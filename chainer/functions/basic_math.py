import math
from numbers import Number

import numpy

from chainer import cuda
from chainer import function
from chainer import variable


# ------------------------------------------------------------------------------
# Arithmetic
# ------------------------------------------------------------------------------


class Neg(function.Function):

    def forward(self, x):
        return -x[0],

    def backward(self, x, gy):
        return -gy[0],


def neg(x):  # -x
    return Neg()(x)


class Add(function.Function):

    def forward(self, x):
        return x[0] + x[1],

    def backward(self, x, gy):
        return gy[0], gy[0]


class AddConstant(function.Function):

    def __init__(self, value):
        self.value = value

    def forward(self, x):
        return x[0] + self.value,

    def backward(self, x, gy):
        return gy[0],


def add(lhs, rhs):  # lhs + rhs
    if isinstance(rhs, variable.Variable):
        return Add()(lhs, rhs)
    return AddConstant(rhs)(lhs)


class Sub(function.Function):

    def forward(self, x):
        return x[0] - x[1],

    def backward(self, x, gy):
        return gy[0], -gy[0]


def sub(lhs, rhs):  # lhs - rhs
    if isinstance(rhs, variable.Variable):
        return Sub()(lhs, rhs)
    return AddConstant(-rhs)(lhs)


class SubFromConstant(function.Function):

    def __init__(self, value):
        self.value = value

    def forward(self, x):
        return self.value - x[0],

    def backward(self, x, gy):
        return -gy[0],


def rsub(lhs, rhs):  # rhs - lhs
    if isinstance(rhs, variable.Variable):
        return Sub()(rhs, lhs)
    return SubFromConstant(rhs)(lhs)


class Mul(function.Function):

    def forward(self, x):
        return x[0] * x[1],

    def backward_cpu(self, x, gy):
        return gy[0] * x[1], gy[0] * x[0]

    def backward_gpu(self, x, gy):
        gx0 = cuda.empty_like(x[0])
        gx1 = cuda.empty_like(x[1])
        cuda.elementwise(
            '''
               float* gx0, float* gx1, const float* x0, const float* x1,
               const float* gy
            ''', '''
               gx0[i] = gy[i] * x1[i];
               gx1[i] = gy[i] * x0[i];
            ''', 'mul_bwd')(gx0, gx1, x[0], x[1], gy[0])
        return gx0, gx1


class MulConstant(function.Function):

    def __init__(self, value):
        self.value = value

    def forward(self, x):
        return self.value * x[0],

    def backward(self, x, gy):
        return self.value * gy[0],


def mul(lhs, rhs):  # lhs * rhs
    if isinstance(rhs, variable.Variable):
        return Mul()(lhs, rhs)
    return MulConstant(rhs)(lhs)


class Div(function.Function):

    def forward(self, x):
        return x[0] / x[1],

    def backward_cpu(self, x, gy):
        gx0 = gy[0] / x[1]
        return gx0, -gx0 * x[0] / x[1]

    def backward_gpu(self, x, gy):
        gx0 = cuda.empty_like(x[0])
        gx1 = cuda.empty_like(x[1])
        cuda.elementwise(
            '''
               float* gx0, float* gx1, const float* x0, const float* x1,
               const float* gy
            ''', '''
               gx0[i] = gy[i] / x1[i];
               gx1[i] = -gx0[i] * x0[i] / x1[i];
            ''', 'div_bwd')(gx0, gx1, x[0], x[1], gy[0])
        return gx0, gx1


def div(lhs, rhs):  # lhs / rhs
    if isinstance(rhs, variable.Variable):
        return Div()(lhs, rhs)
    return MulConstant(1. / rhs)(lhs)


class DivFromConstant(function.Function):

    def __init__(self, value):
        self.value = value

    def forward(self, x):
        return self.value / x[0],

    def backward_cpu(self, x, gy):
        return -self.value * gy[0] / (x[0] ** 2),

    def backward_gpu(self, x, gy):
        gx = cuda.empty_like(x[0])
        if isinstance(self.value, Number):
            cuda.elementwise(
                '''
                   float* gx, const float* x, const float* gy,
                   const float value
                ''',
                'gx[i] = -value * gy[i] / (x[i] * x[i])',
                'div_from_const_bwd')(gx, x[0], gy[0], self.value)
        else:
            cuda.elementwise(
                '''
                   float* gx, const float* x, const float* gy,
                   const float* value
                ''',
                'gx[i] = -value[i] * gy[i] / (x[i] * x[i])',
                'div_from_const_bwd')(gx, x[0], gy[0], self.value)
        return gx,


def rdiv(lhs, rhs):  # rhs / lhs
    if isinstance(rhs, variable.Variable):
        return Div()(rhs, lhs)
    return DivFromConstant(rhs)(lhs)


class PowVarVar(function.Function):

    def forward_cpu(self, x):
        self.y = x[0] ** x[1]
        return self.y,

    def forward_gpu(self, x):
        return x[0] ** x[1],

    def backward_cpu(self, x, gy):
        gx0 = x[1] * (x[0] ** (x[1] - 1)) * gy[0]
        gx1 = numpy.log(x[0]) * self.y * gy[0]
        return gx0, gx1

    def backward_gpu(self, x, gy):
        gx0 = cuda.empty_like(x[0])
        gx1 = cuda.empty_like(x[1])
        cuda.elementwise(
            '''
               float* gx0, float* gx1, const float* x0, const float* x1,
               const float* gy
            ''', '''
               gx0[i] = x1[i] * __powf(x0[i], x1[i] - 1) * gy[i];
               gx1[i] = __logf(x0[i]) * __powf(x0[i], x1[i]) * gy[i];
            ''', 'pow_var_var_bwd')(gx0, gx1, x[0], x[1], gy[0])
        return gx0, gx1


class PowVarConst(function.Function):

    def __init__(self, value):
        self.value = value

    def forward(self, x):
        return x[0] ** self.value,

    def backward_cpu(self, x, gy):
        return self.value * (x[0] ** (self.value - 1)) * gy[0],

    def backward_gpu(self, x, gy):
        gx = cuda.empty_like(x[0])
        if isinstance(self.value, Number):
            cuda.elementwise(
                '''
                   float* gx, const float* x, const float* gy,
                   const float value
                ''',
                'gx[i] = value * __powf(x[i], value - 1) * gy[i]',
                'pow_var_const_bwd')(gx, x[0], gy[0], self.value)
        else:
            cuda.elementwise(
                '''
                   float* gx, const float* x, const float* gy,
                   const float* value
                ''',
                'gx[i] = value[i] * __powf(x[i], value[i] - 1) * gy[i]',
                'pow_var_const_bwd')(gx, x[0], gy[0], self.value)
        return gx,


def pow(lhs, rhs):  # lhs ** rhs
    if isinstance(rhs, variable.Variable):
        return PowVarVar()(lhs, rhs)
    return PowVarConst(rhs)(lhs)


class PowConstVar(function.Function):

    def __init__(self, value):
        self.value = value

    def forward_cpu(self, x):
        self.y = self.value ** x[0]
        return self.y,

    def forward_gpu(self, x):
        y = cuda.empty_like(x[0])
        if isinstance(self.value, Number):
            cuda.elementwise('float* y, const float* x, const float value',
                             'y[i] = __powf(value, x[i])',
                             'pow_const_var_fwd')(y, x[0], self.value)
        else:
            cuda.elementwise('float* y, const float* x, const float *value',
                             'y[i] = __powf(value[i], x[i])',
                             'pow_const_var_fwd')(y, x[0], self.value)
        return y,

    def backward_cpu(self, x, gy):
        return numpy.log(self.value) * self.y * gy[0],

    def backward_gpu(self, x, gy):
        gx = cuda.empty_like(x[0])
        if isinstance(self.value, Number):
            logv = math.log(self.value)
            cuda.elementwise(
                '''
                   float* gx, const float* x, const float* gy,
                   const float value, const float logv
                ''',
                'gx[i] = logv * __powf(value, x[i]) * gy[i]',
                'pow_const_var_bwd')(gx, x[0], gy[0], self.value, logv)
        else:
            cuda.elementwise(
                '''
                   float* gx, const float* x, const float* gy,
                   const float* value
                ''',
                'gx[i] = __logf(value[i]) * __powf(value[i], x[i]) * gy[i]',
                'pow_const_var_bwd')(gx, x[0], gy[0], self.value)
        return gx,


def rpow(lhs, rhs):  # rhs ** lhs
    if isinstance(rhs, variable.Variable):
        return PowVarVar()(rhs, lhs)
    return PowConstVar(rhs)(lhs)


def install_variable_arithmetics():
    variable.Variable.__neg__ = neg
    variable.Variable.__add__ = add
    variable.Variable.__radd__ = add
    variable.Variable.__sub__ = sub
    variable.Variable.__rsub__ = rsub
    variable.Variable.__mul__ = mul
    variable.Variable.__rmul__ = mul
    variable.Variable.__div__ = div
    variable.Variable.__truediv__ = div
    variable.Variable.__rdiv__ = rdiv
    variable.Variable.__rtruediv__ = rdiv
    variable.Variable.__pow__ = pow
    variable.Variable.__rpow__ = rpow

# ------------------------------------------------------------------------------
# Special functions
# ------------------------------------------------------------------------------


class Exp(function.Function):

    def forward_cpu(self, x):
        self.y = numpy.exp(x[0])
        return self.y,

    def forward_gpu(self, x):
        self.y = cuda.cumath.exp(x[0])
        return self.y,

    def backward(self, x, gy):
        return self.y * gy[0],


def exp(x):
    """Elementwise exponential function."""
    return Exp()(x)


class Log(function.Function):

    def forward_cpu(self, x):
        return numpy.log(x[0]),

    def forward_gpu(self, x):
        return cuda.cumath.log(x[0]),

    def backward(self, x, gy):
        return gy[0] / x[0],


def log(x):
    """Elementwise natural logarithm function."""
    return Log()(x)
