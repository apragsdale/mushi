#! /usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as onp
import jax.numpy as np
from typing import Callable


def C(n: int) -> onp.ndarray:
    """The C matrix defined in the text

    n: number of sampled haplotypes
    """
    W1 = onp.zeros((n - 1, n - 1))
    W2 = onp.zeros((n - 1, n - 1))
    b = onp.arange(1, n - 1 + 1)
    # j = 2
    W1[:, 0] = 6 / (n + 1)
    W2[:, 0] = 0
    # j = 3
    W1[:, 1] = 10 * (5 * n - 6 * b - 4) / (n + 2) / (n + 1)
    W2[:, 1] = (20 * (n - 2)) / (n+1) / (n+2)
    for col in range(n - 3):
        # this cast is crucial for floating point precision
        j = onp.float64(col + 2)
        # procedurally generated by Zeilberger's algorithm in Mathematica
        W1[:, col + 2] = -((-((-1 + j)*(1 + j)**2*(3 + 2*j)*(j - n)*(4 + 2*j - 2*b*j + j**2 - b*j**2 + 4*n + 2*j*n + j**2*n)*W1[:, col]) - (-1 + 2*j)*(3 + 2*j)*(-4*j - 12*b*j - 4*b**2*j - 6*j**2 - 12*b*j**2 - 2*b**2*j**2 - 4*j**3 + 4*b**2*j**3 - 2*j**4 + 2*b**2*j**4 + 4*n + 2*j*n - 6*b*j*n + j**2*n - 9*b*j**2*n - 2*j**3*n - 6*b*j**3*n - j**4*n - 3*b*j**4*n + 4*n**2 + 6*j*n**2 + 7*j**2*n**2 + 2*j**3*n**2 + j**4*n**2)*W1[:, col + 1])/(j**2*(2 + j)*(-1 + 2*j)*(1 + j + n)*(3 + b + j**2 - b*j**2 + 3*n + j**2*n)))
        W2[:, col + 2] = ((-1 + j)*(1 + j)*(2 + j)*(3 + 2*j)*(j - n)*(1 + j - n)*(1 + j + n)*W2[:, col] + (-1 + 2*j)*(3 + 2*j)*(1 + j - n)*(j + n)*(2 - j - 2*b*j - j**2 - 2*b*j**2 + 2*n + j*n + j**2*n)*W2[:, col + 1])/((-1 + j)*j*(2 + j)*(-1 + 2*j)*(j - n)*(j + n)*(1 + j + n))

    return W1 - W2


def M(n: int, t: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The M matrix defined in the text

    t: time grid, starting at zero and ending at np.inf
    y: population size in each epoch
    """
    # epoch durations
    s = np.diff(t)
    # we handle the final infinite epoch carefully to facilitate autograd
    u = np.exp(-s[:-1] / y[:-1])
    u = np.concatenate((np.array([1]), u, np.array([0])))

    binom_vec = np.arange(2, n + 1) * (np.arange(2, n + 1) - 1) / 2

    return np.exp(binom_vec[:, np.newaxis]
                  * np.cumsum(np.log(u[np.newaxis, :-1]), axis=1)
                  - np.log(binom_vec[:, np.newaxis])) \
        @ (np.eye(len(y), k=0) - np.eye(len(y), k=-1)) \
        @ np.diag(y)


def prf(Z: np.ndarray, X: np.ndarray, L: np.ndarray) -> np.float64:
    u"""Poisson random field log-likelihood of history

    Z: mutation spectrum history matrix (μ.Z)
    X: k-SFS data
    L: model matrix
    """
    Ξ = L @ Z
    ℓ = (X * np.log(Ξ) - Ξ).sum()
    return ℓ


def d_kl(Z: np.ndarray, X: np.ndarray, L: np.ndarray) -> np.float64:
    u"""generalized Kullback-Liebler divergence between normalized SFS and its
    expectation under history (a Bregman divergence)
    ignores constant term

    Z: mutation spectrum history matrix (μ.Z)
    X: k-SFS data
    L: model matrix
    """
    Ξ = L @ Z
    d_kl = (X * np.log(X / Ξ) - X + Ξ).sum()
    return d_kl


def lsq(Z: np.ndarray, X: np.ndarray, L: np.ndarray) -> float:
    u"""least-squares loss between SFS and its expectation under history

    Z: mutation spectrum history matrix (μ.Z)
    X: k-SFS data
    L: model matrix
    """
    Ξ = L @ Z
    lsq = (1 / 2) * ((Ξ - X) ** 2).sum()
    return lsq


def acc_prox_grad_descent(x: np.ndarray,
                          g: Callable[[np.ndarray], np.float64],
                          grad_g: Callable[[np.ndarray], np.float64],
                          h: Callable[[np.ndarray], np.float64],
                          prox: Callable[[np.ndarray, np.float64], np.float64],
                          tol: np.float64 = 1e-10,
                          max_iter: int = 100,
                          s0: np.float64 = 1,
                          max_line_iter: int = 100,
                          γ: np.float64 = 0.8) -> np.ndarray:
    u"""Nesterov accelerated proximal gradient descent
    https://people.eecs.berkeley.edu/~elghaoui/Teaching/EE227A/lecture18.pdf

    x: initial point
    g: differential term in onjective function
    grad_g: gradient of g
    h: non-differentiable term in objective function
    prox: proximal operator corresponding to h
    tol: relative tolerance in objective function for convergence
    max_iter: maximum number of proximal gradient steps
    s0: initial step size
    max_line_iter: maximum number of line search steps
    γ: step size shrinkage rate for line search
    """
    # initialize step size
    s = s0
    # initialize momentum iterate
    q = x
    # initial objective value
    f = g(x) + h(x)
    print(f'initial cost {f:.6e}', flush=True)
    for k in range(1, max_iter + 1):
        # evaluate differtiable part of objective at momentum point
        g1 = g(q)
        grad_g1 = grad_g(q)
        # store old iterate
        x_old = x
        # Armijo line search
        for line_iter in range(max_line_iter):
            if not np.all(np.isfinite(grad_g1)):
                raise RuntimeError(f'invalid gradient at step {k + 1}, line '
                                   f'search step {line_iter + 1}: {grad_g1}')
            # new point via prox-gradient of momentum point
            x = prox(q - s * grad_g1, s)
            # G_s(q) as in the notes linked above
            G = (1 / s) * (q - x)
            # test g(q - sG_s(q)) for sufficient decrease
            if g(q - s * G) <= (g1 - s * (grad_g1 * G).sum()
                                + (s / 2) * (G ** 2).sum()):
                # Armijo satisfied
                break
            else:
                # Armijo not satisfied
                s *= γ  # shrink step size
        # update momentum term
        q = x + ((k - 1) / (k + 2)) * (x - x_old)
        if line_iter == max_line_iter - 1:
            print('warning: line search failed', flush=True)
            s = s0
        if not np.all(np.isfinite(x)):
            print(f'warning: x contains invalid values', flush=True)
        # terminate if objective function is constant within tolerance
        f_old = f
        f = g(x) + h(x)
        print(f'iteration {k}, cost {f:.6e}', end='        \r', flush=True)
        rel_change = np.abs((f - f_old) / f_old)
        if rel_change < tol:
            print(f'\nrelative change in objective function {rel_change:.2g} '
                  f'is within tolerance {tol} after {k} iterations',
                  flush=True)
            break
        if k == max_iter:
            print(f'\nmaximum iteration {max_iter} reached with relative '
                  f'change in objective function {rel_change:.2g}', flush=True)

    return x


def three_op_prox_grad_descent(x: np.ndarray,
                               g: Callable[[np.ndarray], np.float64],
                               grad_g: Callable[[np.ndarray], np.float64],
                               h1: Callable[[np.ndarray], np.float64],
                               h2: Callable[[np.ndarray], np.float64],
                               prox1: Callable[[np.ndarray, np.float64],
                                               np.float64],
                               prox2: Callable[[np.ndarray, np.float64],
                                               np.float64],
                               tol: np.float64 = 1e-10,
                               max_iter: int = 100,
                               s0: np.float64 = 1,
                               max_line_iter: int = 100,
                               γ: np.float64 = 0.8,
                               ls_tol: np.float64 = 0) -> np.ndarray:
    u"""Three operator splitting proximal gradient descent

    We implement the method of Pedregosa & Gidel (ICML 2018),
    including backtracking line search.

    The optimization problem solved is:

      min_x g(x) + h1(x) + h2(x)

    where g is differentiable, and the proximal operators for h1 and h2 are
    available.

    x: initial point
    g: differential term in objective function
    grad_g: gradient of g
    h1: 1st non-differentiable term in objective function
    h2: 2nd non-differentiable term in objective function
    prox1: proximal operator corresponding to h1
    prox2: proximal operator corresponding to h2
    tol: relative tolerance in objective function for convergence
    max_iter: maximum number of proximal gradient steps
    s0: step size
    max_line_iter: maximum number of line search steps
    γ: step size shrinkage rate for line search
    ls_tol: line search tolerance
    """

    # initial objective value
    s = s0
    z = x
    u = np.zeros_like(z)
    f = g(x) + h1(x) + h2(x)
    print(f'initial cost {f:.6e}', flush=True)

    for k in range(1, max_iter + 1):
        # evaluate differentiable part of objective
        g1 = g(z)
        grad_g1 = grad_g(z)
        if not np.all(np.isfinite(grad_g1)):
            raise RuntimeError(f'invalid gradient at step {k + 1}: {grad_g1}')
        # store old iterate
        # x_old = x
        # Armijo line search
        for line_iter in range(max_line_iter):
            # new point via prox-gradient of momentum point
            x = prox1(z - s * (u + grad_g1), s)
            # quadratic approximation of cost
            Q = (g1 + (grad_g1 * (x - z)).sum()
                  + ((x - z) ** 2).sum() / (2 * s))
            if g(x) - Q <= ls_tol:
                # sufficient decrease satisfied
                break
            else:
                # sufficient decrease not satisfied
                s *= γ  # shrink step size
        if line_iter == max_line_iter - 1:
            print('warning: line search failed', flush=True)

        # update z variables with 2nd prox
        z = prox2(x + s * u, s)
        # update u variables: dual variables
        u = u + (x - z) / s
        # grow step size
        s = min(s / γ**2, s0)

        # TODO: convergence based on dual certificate
        if not np.all(np.isfinite(x)):
            print(f'warning: x contains invalid values', flush=True)
        # terminate if objective function is constant within tolerance
        f_old = f
        # DIFFERENCE FROM PAPER: use z as next iterate
        f = g(z) + h1(z) + h2(z)
        print(f'iteration {k}, cost {f:.6e}', end='        \r', flush=True)
        rel_change = np.abs((f - f_old) / f_old)
        if rel_change < tol:
            print(f'\nrelative change in objective function {rel_change:.2g} '
                  f'is within tolerance {tol} after {k} iterations',
                  flush=True)
            break
        # if certificate < tol:
        #     print(f'certificate norm {certificate:.2g} '
        #           f'is within tolerance {tol} after {k} iterations')
        #     break
        if k == max_iter:
            print(f'\nmaximum iteration {max_iter} reached with relative '
                  f'change in objective function {rel_change:.2g}', flush=True)

    return z
