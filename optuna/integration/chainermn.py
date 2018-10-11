from __future__ import absolute_import

from typing import Callable  # NOQA
from typing import Optional  # NOQA
from typing import Tuple  # NOQA
from typing import Type  # NOQA

from optuna.storages import InMemoryStorage
from optuna.study import Study  # NOQA
from optuna.trial import Trial  # NOQA

try:
    from chainermn.communicators.communicator_base import CommunicatorBase  # NOQA
    _available = True
except ImportError as e:
    _import_error = e
    _available = False


class ChainerMNObjectiveFunc(object):
    def __init__(self, func, comm):
        # type: (Callable[[Trial, CommunicatorBase], float], CommunicatorBase) -> None

        self.comm = comm
        self.objective = func

    def __call__(self, trial):
        # type: (Trial) -> float

        self.comm.mpi_comm.bcast((True, trial.trial_id))
        return self.objective(trial, self.comm)


class ChainerMNStudy(object):
    def __init__(
        self,
        study,  # type: Study
        comm,  # type: CommunicatorBase
    ):
        # type: (...) -> None

        _check_chainermn_availability()

        if isinstance(study.storage, InMemoryStorage):
            raise ValueError('ChainerMN integration is not available with InMemoryStorage.')

        study_names = comm.mpi_comm.allgather(study.study_name)
        if len(set(study_names)) != 1:
            raise ValueError('Please make sure an identical study name is shared among workers.')

        super(ChainerMNStudy, self).__setattr__('delegate', study)
        super(ChainerMNStudy, self).__setattr__('comm', comm)

    def run(
        self,
        func,  # type: Callable[[Trial, CommunicatorBase], float]
        n_trials=None,  # type: Optional[int]
        timeout_seconds=None,  # type: Optional[float]
        n_jobs=1,  # type: int
        catch=(Exception,),  # type: Tuple[Type[Exception]]
    ):
        # type: (...) -> None

        if self.comm.rank == 0:
            func_mn = ChainerMNObjectiveFunc(func, self.comm)
            self.delegate.run(func_mn, n_trials, timeout_seconds, n_jobs, catch)
            self.comm.mpi_comm.bcast((False, None))
        else:
            while True:
                has_next_trial, trial_id = self.comm.mpi_comm.bcast(None)
                if not has_next_trial:
                    break
                trial = Trial(self.delegate, trial_id)
                func(trial, self.comm)

    def __getattr__(self, attr_name):
        return getattr(self.delegate, attr_name)

    def __setattr__(self, attr_name, value):
        setattr(self.delegate, attr_name, value)


def _check_chainermn_availability():
    # type: () -> None

    if not _available:
        raise ImportError(
            'ChainerMN is not available. Please install ChainerMN to use this feature. '
            'ChainerMN can be installed by executing `$ pip install chainermn`. '
            'For further information, please refer to the installation guide of ChainerMN. '
            '(The actual import error is as follows: ' + str(_import_error) + ')')
