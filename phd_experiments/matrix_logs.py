# https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.logm.html
# https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.expm.html
# https://www.simiode.org/resources/6425/download/5-010-Text-S-MatrixExponential-StudentVersion.pdf
# https://web.mit.edu/18.06/www/Spring17/Matrix-Exponentials.pdf
# https://proofwiki.org/wiki/Decomposition_of_Matrix_Exponential
# https://www.maths.manchester.ac.uk/~higham/talks/ecm12_log.pdf
# https://www.ias.edu/sites/default/files/sns/files/1-matrixlog_tex(1).pdf
# http://scipp.ucsc.edu/~haber/webpage/MatrixExpLog.pdf
# https://arxiv.org/abs/math/0410556
# https://nhigham.com/2020/11/17/what-is-the-matrix-logarithm/
# https://www.mdpi.com/2227-7390/9/17/2018
# https://math.stackexchange.com/questions/3950704/integral-representation-of-matrix-logarithm
# http://bayanbox.ir/view/2190529855266466427/Nicholas-J.Higham-Functionsof-Matrices-Theory.pdf
# http://bayanbox.ir/view/2190529855266466427/Nicholas-J.Higham-Functionsof-Matrices-Theory.pdf
# exponential of a tensor https://onlinelibrary.wiley.com/doi/pdf/10.1002/9780470694626.app2
# matrix log in pytorch https://stackoverflow.com/questions/73288332/is-there-a-way-to-compute-the-matrix-logarithm-of-a-pytorch-tensor
# https://core.ac.uk/download/pdf/144007506.pdf pade and gregory

# Eigen Values for Tensor-Train Format
# https://cscproxy.mpi-magdeburg.mpg.de/preprints/2011/MPIMD11-09.pdf

import numpy as np
import scipy.linalg
import torch
from scipy.integrate import solve_ivp
from phd_experiments.torch_ode_solvers.torch_rk45 import TorchRK45

# TODO
# https://bayanbox.ir/view/2190529855266466427/Nicholas-J.Higham-Functionsof-Matrices-Theory.pdf
# eq 11.1 and eq 11.16

def log_matrix_gregory():
    # https://bayanbox.ir/view/2190529855266466427/Nicholas-J.Higham-Functionsof-Matrices-Theory.pdf
    # eq 11.16
    pass
def log_matrix_integral_form(A: torch.Tensor) -> torch.Tensor:
    # Functions of matrices Book by Nicholas Higham : 2008
    # http://bayanbox.ir/view/2190529855266466427/Nicholas-J.Higham-Functionsof-Matrices-Theory.pdf p269 eqn 11.1
    def log_ode_func(t, A):
        A = A.view(A.size()[0], A.size()[1])
        assert len(A.size()) == 2
        assert A.size()[0] == A.size()[1]
        I = torch.eye(n=A.size()[0])
        term1 = A - I
        term2 = torch.inverse(t * (A - I) + I)
        res = torch.matmul(term1, term2)
        res = res.view(1, res.size()[0], res.size()[1])
        return res

    soln = solve_ivp(device=torch.device('cpu'), tensor_dtype=A.dtype)
    # FIXME, use
    # soln = sc.solve_ivp(func=log_ode_func, t_span=(0, 1), z0=torch.zeros(size=(1, A.size()[0], A.size()[1])),
    #                         args=None)
    yT = soln.z_trajectory[-1]
    A_np = A.detach().numpy()
    logA = scipy.linalg.logm(A_np)
    return yT


def log_matrix_taylor_series(A: np.ndarray, M=1000, scipy_validate=False, eps=1e-4) -> np.ndarray:
    """
    log of a matrix via tailor expansion
    Refs:
    http://scipp.ucsc.edu/~haber/webpage/MatrixExpLog.pdf : eqn(80)
    http://www.math.com/tables/expansion/log.htm
    """
    I = np.identity(A.shape[0])
    assert A.shape[0] == A.shape[1], f"Matrix must be square dim1={A.shape[0]} != dim2={A.shape[1]}"
    assert isinstance(A, np.ndarray), f"Matrix must be of type np.ndarray, got {type(A)}"
    if np.linalg.norm(A - I) > 1:
        print(f"||A-I||>1 , norm = {np.linalg.norm(A - I)}")
    logA = np.zeros((A.shape[0], A.shape[1]))

    sign = 1.0
    A_minus_I_pow = A - I
    for m in range(1, M + 1):
        logA += sign / m * A_minus_I_pow
        A_minus_I_pow = np.matmul(A_minus_I_pow, A - I)
        sign *= -1
    if scipy_validate:
        logA_scipy = scipy.linalg.logm(A)
        norm_err = np.linalg.norm(logA - logA_scipy)
        assert norm_err <= eps, f"scipy_validation failed : norm err = {norm_err}>eps = {eps}"
    return logA


def log_taylor_series_mtx_draft(A: torch.Tensor):
    # http://scipp.ucsc.edu/~haber/webpage/MatrixExpLog.pdf eqn 80
    # assert len(A.size()) == 2, "A must be a matrix"
    # assert A.size()[0] == A.size()[1], " A must be symmetric"
    I = np.identity(2)
    logA_scipy = scipy.linalg.logm(A)  # as a ref
    norm_A_minus_I = scipy.linalg.norm(A - I)
    eig = scipy.linalg.eigvals(A)
    if norm_A_minus_I > 1:
        print(f'warning : norm_A_minus_I = {norm_A_minus_I} > 1')
    M = 1000
    logA = np.zeros(shape=(2, 2))
    # A_scalar = A[0][0]
    # logA_scalar = 0
    # A_minus_I_pow = A-I
    sign = 1
    for m in range(1, M + 1):
        denum = 1.0 / m
        pow_term = np.linalg.matrix_power(A - I, m)
        # pow_term_scalar = np.power(A_scalar-1,m)
        term_mtx = sign * denum * pow_term
        # term_scalar = sign * denum * pow_term_scalar
        logA += term_mtx
        # logA_scalar += term_scalar
        sign *= -1
        # A_minus_I_pow = torch.matmul(A_minus_I_pow, A-I)
    err = scipy.linalg.norm(logA - logA_scipy)
    # err2 = scipy.linalg.norm(logA_scalar - logA_scipy[0][0])
    return None


if __name__ == '__main__':
    # for i in range(10):
    #     A = np.random.uniform(low=0.01, high=0.02, size=(2, 2))
    #     print(f'sample {i} , A= {A}')
    #     logA = log_matrix_taylor_series(A=A, scipy_validate=True, eps=0.1)

    logA = np.array([[0.5]])
    A = scipy.linalg.expm(logA)
    logA_ = log_matrix_integral_form(A=torch.Tensor(A))
