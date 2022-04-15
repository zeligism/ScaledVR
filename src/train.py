
import time
import argparse
import pickle
import os
import numpy as np
import matplotlib.pyplot as plt
import sklearn
import scipy
from joblib import Memory
from sklearn.datasets import load_svmlight_file
from sklearn.preprocessing import normalize

import optimizer as OLD
from optimizer_new import *
from plot import *

mem = Memory("./mycache")
DATASET_DIR = "datasets"
DATASETS = ("a1a", "a9a", "rcv1", "covtype", "real-sim", "w8a", "ijcnn1", "news20",)
# @TODO: allow case-insensitive arg for optimizer, but keep canonical name
OPTIMIZERS = ("SGD", "SARAH", "PAGE", "OASIS", "SVRG", "L-SVRG", "LSVRG", "Adam", "Adagrad", "Adadelta")
#OPTIMIZERS = ("sgd", "sarah", "page", "oasis", "svrg", "l-svrg", "lsvrg", "adam", "adagrad", "adadelta")


def parse_args(namespace=None):
    parser = argparse.ArgumentParser(description="Optimizers with diagonal preconditioning")

    parser.add_argument("-s", "--seed", type=int, default=None,
                        help='Random seed')
    parser.add_argument("--dataset", type=str, choices=DATASETS, default="a1a",
                        help="Name of dataset (in 'datasets' directory")
    parser.add_argument("--corrupt", nargs="*", type=int, default=None,
                        help="Corrupt scale features in dataset."
                        "First two args = (k_min, k_max) = range of scaling in powers."
                        "If one arg is given, range will be (-k,k).")
    parser.add_argument("--savefig", type=str, default=None,
                        help="Save plots under this name (default: don't save).")
    parser.add_argument("--savedata", type=str, default=None,
                        help="Save data log (default: don't save).")

    parser.add_argument("--optimizer", type=str, choices=OPTIMIZERS, default="SARAH",
                        help="Name of optimizer.")
    parser.add_argument("-T", "--epochs", dest="T", type=int, default=5,
                        help="Number of epochs to run.")
    parser.add_argument("-BS", "--batch_size", dest="BS", type=int, default=1,
                        help="Batch size.")
    parser.add_argument("-lr", "--gamma", dest="lr", type=float, default=0.02,
                        help="Base learning rate.")
    parser.add_argument("--lr-decay", type=float, default=0,
                        help="Learning rate decay.")
    parser.add_argument("--weight-decay", "--lam", "--lmbd", type=float, default=0,
                        help="weight decay / n")
    parser.add_argument("-p", "--update-p", dest="p", type=float, default=0.99,
                        help="Probability p in L-SVRG or PAGE.")

    parser.add_argument("--precond", type=str.lower, default=None,
                        help="Diagonal preconditioner (default: none).")
    parser.add_argument("--beta1", type=float, default=0.999,
                        help="Momentum of gradient first moment.")
    parser.add_argument("--beta2", "--beta", "--rho", dest="beta2", type=float, default=0.999,
                        help="Momentum of gradient second moment.")
    parser.add_argument("--alpha", type=float, default=1e-7,
                        help="Equivalent to 'eps' in Adam (e.g. see pytorch docs).")
    parser.add_argument("--precond_warmup", type=int, default=100,
                        help="Num of samples for initializing diagonal in hutchinson's method.")
    parser.add_argument("--precond_resample", action="store_true",
                        help="Resample batch in hutchinson's method.")
    parser.add_argument("--precond_zsamples", type=int, default=1,
                        help="Num of rademacher samples in hutchinson's method.")

    parser.add_argument("--old", action="store_true", help="Use old optimization code (for testing).")

    # Parse command line args
    args = parser.parse_args(namespace=namespace)
    return args


@mem.cache
def get_data(filePath):
    data = load_svmlight_file(filePath)
    return data[0], data[1]


def corrupt_scale(X, k_min=-3, k_max=3):
    bad_scale = 10**np.linspace(k_min, k_max, X.shape[1])
    np.random.shuffle(bad_scale)
    return X[:].multiply(bad_scale.reshape(1,-1)).tocsr()


def savedata(data, fname):
    with open(fname, 'wb') as f:
        pickle.dump(data, f)


def train(args):
    # check if dataset is downloaded
    args.dataset = os.path.join(DATASET_DIR, args.dataset)
    if not os.path.isfile(args.dataset):
        raise FileNotFoundError(f"Could not find dataset at '{args.dataset}'")
    print(f"Using dataset '{args.dataset}'.")
    # Set seed if given
    if args.seed is not None:
        np.random.seed(args.seed)
        print(f"Setting random seed to {args.seed}.")

    X, y = get_data(args.dataset)
    X = normalize(X, norm='l2', axis=1)
    print("We have %d samples, each has up to %d features." % (X.shape[0], X.shape[1]))

    if args.corrupt is not None:
        if len(args.corrupt) == 0:
            args.corrupt = (-1,1)
        elif len(args.corrupt) == 1:
            args.corrupt = (-args.corrupt[0], args.corrupt[0])
        print(f"Scaling features from 10^{args.corrupt[0]} to 10^{args.corrupt[0]}.")
        X = corrupt_scale(X, args.corrupt[0], args.corrupt[1])

    print(f"Running {args.optimizer}...")
    kwargs = dict(T=args.T, BS=args.BS, gamma=args.lr,
                  lam=args.weight_decay,
                  precond=args.precond,
                  beta=args.beta2, alpha=args.alpha,
                  precond_warmup=args.precond_warmup,
                  precond_resample=args.precond_resample,
                  precond_zsamples=args.precond_zsamples,
                  )
    new_kwargs = dict(T=args.T, BS=args.BS, lr=args.lr,
                      lr_decay=args.lr_decay, weight_decay=args.weight_decay,
                      precond=args.precond,
                      beta1=args.beta1, beta2=args.beta2, alpha=args.alpha,
                      precond_warmup=args.precond_warmup,
                      precond_resample=args.precond_resample,
                      precond_zsamples=args.precond_zsamples,
                      )

    start_time = time.time()
    if args.optimizer == "SGD":
        if args.old:
            wopt, data = OLD.SGD(X, y, **kwargs)
        else:
            wopt, data = run_SGD(X, y, **new_kwargs)
    elif args.optimizer == "SARAH":
        if args.old:
            wopt, data = OLD.SARAH(X, y, **kwargs)
        else:
            wopt, data = run_SARAH(X, y, **new_kwargs)
    elif args.optimizer == "SVRG":
        if args.old:
            wopt, data = OLD.SVRG(X, y, **kwargs)
        else:
            wopt, data = run_SVRG(X, y, **new_kwargs)
    elif args.optimizer in ("L-SVRG", "LSVRG"):
        if args.old:
            wopt, data = OLD.L_SVRG(X, y, p=args.p, **kwargs)
        else:
            wopt, data = run_LSVRG(X, y, p=args.p, **new_kwargs)
    elif args.optimizer == "Adam":
        if args.old:
            wopt, data = OLD.Adam(X, y, **kwargs)
        else:
            wopt, data = run_Adam(X, y, **new_kwargs)
    elif args.optimizer == "Adagrad":
        wopt, data = NEW.run_Adagrad(X, y, **new_kwargs)
    elif args.optimizer == "Adadelta":
        wopt, data = NEW.run_Adadelta(X, y, **new_kwargs)
    elif args.optimizer == "PAGE":
        wopt, data = NEW.run_PAGE(X, y, p=args.p, **new_kwargs)
    elif args.optimizer == "OASIS":
        wopt, data = OASIS(X, y, **kwargs)  # @XXX
    else:
        raise NotImplementedError(f"Optimizer '{args.optimizer}' not implemented yet.")

    print("Done.")
    print(f"Running time: {time.time() - start_time:.2f} seconds.")

    if args.savefig is not None:
        # Make a nice title
        title = rf"{args.optimizer}({os.path.basename(args.dataset)})"
        title += rf" with BS={args.BS}, $\gamma$={args.lr}"
        if args.weight_decay != 0.0:
            title += rf", $\lambda$={args.weight_decay}"
        if args.optimizer == "L-SVRG":
            title += f", p={args.p}"
        if args.precond is not None:
            title += f", precond={args.precond}"
        if args.precond == "hutchinson":
            title += rf", $\beta$={args.beta2}, $\alpha$={args.alpha}"
        if args.corrupt is not None:
            title += f", corrupt=[{args.corrupt[0]}, {args.corrupt[1]}]"
        print(f"Saving plot to '{args.savefig}'.")
        savefig2(data, args.savefig, title=title)

    if args.savedata is not None:
        print(f"Saving data to '{args.savedata}'.")
        savedata(data, args.savedata)


def main():
    args = parse_args()
    train(args)


if __name__ == "__main__":
    main()
