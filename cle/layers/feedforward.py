import ipdb
import numpy as np
import theano
import theano.tensor as T

from cle.cle.layers import StemCell

from itertools import izip

from theano.compat.python2x import OrderedDict


class FullyConnectedLayer(StemCell):
    """
    Fully connected layer

    Parameters
    ----------
    .. todo::
    """
    def fprop(self, X, tparams, ndim=None):

        if len(X) != len(self.parent):
            raise AttributeError("The number of inputs does not match "
                                 "with the number of parents.")

        # X could be a list of inputs.
        # depending the number of parents.
        if ndim is None:
            ndims = [x.ndim for x in X]
            idx = np.argmax(ndims)
            ndim = np.maximum(np.array(ndims).max(), 2)

        z_shape = [X[idx].shape[i] for i in xrange(ndim-1)] + [self.nout]
        z = T.zeros(z_shape, dtype=theano.config.floatX)

        for x, (parname, parout) in izip(X, self.parent.items()):
            W = tparams['W_'+parname+'__'+self.name]

            if x.ndim == 1:
                if 'int' not in x.dtype:
                    x = T.cast(x, 'int64')
                if z.ndim == 2:
                    z += W[x]
                elif z.ndim == 3:
                    z += W[x][None, :, :]
            elif x.ndim == 2:
                if ndim == 2:
                    z += T.dot(x[:, :parout], W)
                if ndim == 3:
                    z += T.dot(x[:, :parout], W)[None, :, :]
            elif x.ndim == 3:
                if z.ndim != 3:
                    raise ValueError("your target ndim is less than the source ndim")
                z += T.dot(x[:, :, :parout], W)

        if not hasattr(self, 'use_bias'):
            z += tparams['b_'+self.name]
        elif self.use_bias:
            z += tparams['b_'+self.name]

        if z.ndim == 3:
            z_shape = z.shape
            z = self.nonlin(z.reshape((z_shape[0]*z_shape[1], -1))).reshape((z_shape[0], z_shape[1], -1))
            z += self.cons
        elif z.ndim == 2:
            z = self.nonlin(z) + self.cons
        z.name = self.name

        return z


class GRBM(StemCell):
    """
    Gaussian restrcited Boltzmann Machine

    Parameters
    ----------
    .. todo::
    """
    def __init__(self,
                 k_step=1,
                 **kwargs):
        super(GRBM, self).__init__(**kwargs)
        self.k_step = k_step

    def initialize(self):

        params = OrderedDict()
        parname, parout = self.parent.items()[0]
        W_shape = (parout, self.nout)
        W_name = 'W_' + parname + '__' + self.name
        params[W_name] = self.init_W.get(W_shape)

        return params

    def fprop(self, X):

        if len(X) != len(self.parent):
            raise AttributeError("The number of inputs doesn't match "
                                 "with the number of parents.")
        # X could be a list of inputs.
        # depending the number of parents.
        v = X[0]
        for i in xrange(self.k_step):
            v_mean, v, h_mean, h = self.gibbs_step(v, X[1], X[2], X[3])

        return v, h

    def gibbs_step(self, x, bh, bx, x_sig, tparams):

        parname, parout = self.parent.items()[0]
        W = tparams['W_'+parname+'__'+self.name]
        h_mean = T.nnet.sigmoid(T.dot(x[:, :parout]/(x_sig**2), W) + bh)
        h = self.theano_rng.binomial(size=h_mean.shape, n=1, p=h_mean,
                                     dtype=theano.config.floatX)
        v_mean = T.dot(h, W.T) + bx
        epsilon = self.theano_rng.normal(size=v_mean.shape, avg=0., std=1.,
                                         dtype=theano.config.floatX)
        v = v_mean + x_sig * epsilon

        return v_mean, v, h_mean, h

    def free_energy(self, v, X, tparams):

        W = tparams['W_'+parname+'__'+self.name]
        squared_term = 0.5 * ((X[2] - v) / X[3])**2
        hid_inp = T.dot(v / (X[3]**2), W) + X[1]
        FE = squared_term.sum(axis=1) - T.nnet.softplus(hid_inp).sum(axis=1)

        return FE

    def cost(self, X, tparams):

        v_mean, v, h_mean, h = self.gibbs_step(X)

        return (self.free_energy(X[0], X, tparams) - self.free_energy(v, X, tparams)).mean()

    def sample(self, X):

        mu = X[0]
        sig = X[1]
        coeff = X[2]
        mu = mu.reshape((mu.shape[0],
                         mu.shape[1]/coeff.shape[-1],
                         coeff.shape[-1]))
        sig = sig.reshape((sig.shape[0],
                           sig.shape[1]/coeff.shape[-1],
                           coeff.shape[-1]))
        idx = predict(
            self.theano_rng.multinomial(
                pvals=coeff,
                dtype=coeff.dtype
            ),
            axis=1
        )
        mu = mu[T.arange(mu.shape[0]), :, idx]
        sig = sig[T.arange(sig.shape[0]), :, idx]
        epsilon = self.theano_rng.normal(size=mu.shape,
                                         avg=0., std=1.,
                                         dtype=mu.dtype)
        z = mu + sig * epsilon

        return z
