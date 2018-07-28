from cvxopt import matrix, spmatrix
from cvxopt import mul, div, exp
from ..consts import *
from .base import ModelBase


class COI(ModelBase):
    def __init__(self, system, name):
        super(COI, self).__init__(system, name)
        self._data.update({'syn': None,
                           'Td': 1,
                           })
        self._descr.update({'syn': 'synchronous generator list',
                            'Td': 'washout filter time constant',
                            })
        self._params.extend({'Td'})
        self._algebs.extend(['delta', 'omega', 'dwdt'])
        self._states.extend(['xdw'])
        self.calls.update({'init1': True, 'gcall': True,
                           'fcall': True, 'jac0': True,
                           })
        self._service.extend(['H', 'M', 'Mtot', 'usyn', 'gdelta', 'gomega', 'iTd'])
        self._fnamey.extend(['\\delta', '\\omega', '\\frac{d\\omega}{dt}'])
        self._fnamex.extend(['x\\omega'])
        self._meta_to_attr()

    def init1(self, dae):
        for item in self._service:
            self.__dict__[item] = [[]] * self.n

        dae.y[self.omega] = 1
        for idx, item in enumerate(self.syn):
            self.usyn[idx] = self.read_field_ext('Synchronous', field='u', idx=item)
            self.M[idx] = self.read_field_ext('Synchronous', field='M', idx=item)
            self.Mtot[idx] = sum(self.M[idx])
            self.gdelta[idx] = self.read_field_ext('Synchronous', field='delta', idx=item)
            self.gomega[idx] = self.read_field_ext('Synchronous', field='omega', idx=item)

            dae.y[self.delta[idx]] = sum(mul(self.M[idx], dae.x[self.gdelta[idx]])) / self.Mtot[idx]

        self.iTd = div(self.u, self.Td)
        dae.x[self.xdw] = self.iTd

    def gcall(self, dae):
        for idx in range(self.n):
            dae.g[self.omega[idx]] = dae.y[self.omega[idx]] - sum(mul(self.M[idx], dae.x[self.gomega[idx]])) / self.Mtot[idx]
            dae.g[self.delta[idx]] = dae.y[self.delta[idx]] - sum(mul(self.M[idx], dae.x[self.gdelta[idx]])) / self.Mtot[idx]
        dae.g[self.dwdt] = (mul(self.iTd, dae.y[self.omega]) - dae.x[self.xdw]) - dae.y[self.dwdt]

    def jac0(self, dae):
        dae.add_jac(Gy0, 1, self.omega, self.omega)
        dae.add_jac(Gy0, 1, self.delta, self.delta)

        dae.add_jac(Gy0, self.iTd, self.dwdt, self.omega)
        dae.add_jac(Gx0, -1, self.dwdt, self.xdw)

        dae.add_jac(Fy0, self.iTd **2, self.xdw, self.omega)
        dae.add_jac(Fx0, -self.iTd, self.xdw, self.xdw)

        dae.add_jac(Gy0, -1, self.dwdt, self.dwdt)

    def fcall(self, dae):
        dae.f[self.xdw] = mul(self.iTd, mul(self.iTd, dae.y[self.omega]) - dae.x[self.xdw])

    # def fcall(self, dae):
    #     for idx in range(self.n):
    #         dae.f[self.gdelta[idx]] += 2*pi*self.system.Settings.freq *(1 - dae.y[self.omega[idx]])
    #
    # def fxcall(self, dae):
    #     for idx in range(self.n):
    #         dae.add_jac(Fy, -2*pi*self.system.Settings.freq, self.gdelta[idx], self.omega[idx])
    #         dae.add_jac(Gx, -self.M[idx] / self.Mtot[idx], self.gomega[idx], self.gomega[idx])
    #         dae.add_jac(Gx, -self.M[idx] / self.Mtot[idx], self.delta[idx], self.delta[idx])

