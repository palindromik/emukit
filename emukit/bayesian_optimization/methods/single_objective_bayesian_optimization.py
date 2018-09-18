from enum import Enum, auto
import numpy as np

from GPy.models import GPRegression
from GPy.kern import Matern52

from ...model_wrappers.gpy_model_wrappers import GPyModelWrapper
from ...core.parameter_space import ParameterSpace
from ...core.loop import FixedIterationsStoppingCondition, UserFunction
from ..acquisitions import ExpectedImprovement, NegativeLowerConfidenceBound, ProbabilityOfImprovement
from ..loops import BayesianOptimizationLoop


class AcquisitionType(Enum):
    EI = auto()
    PI = auto()
    NLCB = auto()


class OptimizerType(Enum):
    LBFGS = auto()


class GPBayesianOptimization(BayesianOptimizationLoop):
    def __init__(self, variables_list: list, X: np.array, Y: np.array, noiseless: bool = False,
                 acquisition_type: AcquisitionType = AcquisitionType.EI, normalize_Y: bool = True,
                 acquisition_optimizer_type: OptimizerType = OptimizerType.LBFGS,
                 model_update_interval: int = int(1)) -> None:

        """
        Generic class to run Bayesian optimization with GPyRegression model.

        Dependencies:
            GPy (https://github.com/SheffieldML/GPy)

        :param variables_list: list containing the definition of the variables of the input space.
        :param noiseless:  determines whether the objective function is noisy or not
        :param X: initial input values where the objective has been evaluated.
        :param Y: initial output values where the objective has been evaluated.
        :param acquisition_type: type of acquisition to use during optimization.
            - EI: Expected improvement
            - PI: Probability of improvement
            - NLCB: Negative lower confidence bound
        :param normalize_Y: whether the outputs of Y are normalized in the model.
        :param acquisition_optimizer_type: selects the type of optimizer of the acquisition.
            - LBFGS: uses L-BFGS with multiple initializations.
        :param model_update_interval: interval of interactions in which the model is updated.
        """

        self.variables_list = variables_list
        self.noiseless = noiseless
        self.X = X
        self.Y = Y
        self.acquisition_type = acquisition_type
        self.normalize_Y = normalize_Y
        self.acquisition_optimizer_type = acquisition_optimizer_type
        self.model_update_interval = model_update_interval

        # 1. Crete the internal object to handle the input space
        self.space = ParameterSpace(variables_list)

        # 2. Select the model to use in the optimization
        self._model_chooser()

        # 3. Select the acquisition function
        self._acquisition_chooser()

        # 4. Select how the objective is going to be evaluated
        self._evaluator_chooser()

        super(GPBayesianOptimization, self).__init__(model=self.model,
                                                     space=self.space,
                                                     acquisition=self.acquisition,
                                                     X_init=X,
                                                     Y_init=Y,
                                                     candidate_point_calculator=self.evaluator)

    def _model_chooser(self):
        """ Initialize the model used for the optimization """
        kernel = Matern52(len(self.variables_list), variance=1., ARD=False)
        gpmodel = GPRegression(self.X, self.Y, kernel)
        gpmodel.optimize()
        self.model = GPyModelWrapper(gpmodel)
        if self.noiseless:
            gpmodel.Gaussian_noise.constrain_fixed(0.001)
        self.model = GPyModelWrapper(gpmodel)

    def _acquisition_chooser(self):
        """ Select the acquisition function used in the optimization """
        if self.acquisition_type is AcquisitionType.EI:
            self.acquisition = ExpectedImprovement(self.model)
        elif self.acquisition_type is AcquisitionType.PI:
            self.acquisition = ProbabilityOfImprovement(self.model)
        elif self.acquisition_type is AcquisitionType.NLCB:
            self.acquisition = NegativeLowerConfidenceBound(self.model)

    def _evaluator_chooser(self):
        """ Selects whether the optimization is done sequentially or in parallel"""
        self.evaluator = None

    def suggest_new_locations(self):
        """ Returns one or a batch of locations without evaluating the objective """
        return self.candidate_point_calculator.compute_next_points(self.loop_state)[0].X

    def run_optimization(self, user_function: UserFunction, num_iterations: int) -> None:
        """
        :param user_function: The function that we want to optimize
        :param num_iterations: The number of iterations to run the Bayesian optimization loop.
        """
        self.run_loop(user_function, FixedIterationsStoppingCondition(num_iterations))
