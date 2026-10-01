"""BasinForge: a calibration/workflow layer on explicitly identified model engines."""
from .data import Basin
from .models import Model, get_model, list_models
from .calibration import CalibrationConfig, CalibrationResult, calibrate, calibrate_shared
from .batch import calibrate_many, compare_models
from .metrics import evaluate, nse, kge, rmse, log_nse
from .marrmot import configure_marrmot, check_marrmot, close_marrmot, marrmot_details
from .analysis import calibrate_multistart, simulate_ensemble
from .report import export_report
from .sensitivity import morris_sensitivity, sobol_sensitivity
from .experiment import run_experiment

__version__ = "0.2.0"
__all__ = ["Basin", "Model", "get_model", "list_models", "CalibrationConfig", "CalibrationResult", "calibrate", "calibrate_shared", "calibrate_many", "compare_models", "evaluate", "nse", "kge", "rmse", "log_nse"]
__all__ += ["configure_marrmot", "check_marrmot", "close_marrmot", "marrmot_details", "calibrate_multistart", "simulate_ensemble", "export_report", "morris_sensitivity", "sobol_sensitivity", "run_experiment"]
