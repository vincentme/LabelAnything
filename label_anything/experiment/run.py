import os
from label_anything.data import get_dataloaders
from label_anything.logger.text_logger import get_logger
from label_anything.experiment.parameters import parse_params
import sys
import comet_ml
from copy import deepcopy

from label_anything.logger.image_logger import Logger
from label_anything.experiment.train_model import train_and_test
from label_anything.models import model_registry

logger = get_logger(__name__)


def comet_experiment(comet_information: dict, params: dict):
    global logger
    logger_params = deepcopy(params.get("logger", {}))
    logger_params.pop("comet", None)
    if os.environ.get("TMPDIR", None) or os.environ.get("TMP", None) or os.environ.get("TEMP", None):
        if os.environ.get("TMPDIR", None):
            tmp_dir = os.environ.get("TMPDIR")
        elif os.environ.get("TMP", None):
            tmp_dir = os.environ.get("TMP")
        else:
            tmp_dir = os.environ.get("TEMP")
        logger.info(f"Using {tmp_dir} as temporary directory from environment variables")
        logger_params["tmp_dir"] = tmp_dir
    else:
        tmp_dir = logger_params.get("tmp_dir", None)
        logger.info(f"No temporary directory found in environment variables, using {tmp_dir} for images")
    os.makedirs(tmp_dir, exist_ok=True)
    
    if comet_information.get("offline"):
        offdir = comet_information.pop("offline_directory", None)
        experiment = comet_ml.OfflineExperiment(offline_directory=offdir)
    else:
        experiment = comet_ml.Experiment()
    comet_ml.init(comet_information)
    experiment.add_tags(comet_information.get("tags"))
    experiment.log_parameters(params)
    
    logger = Logger(experiment, **logger_params)
    
    return logger


class Run:
    def __init__(self):
        self.kd = None
        self.params = None
        self.dataset = None
        self.experiment = None
        self.comet_logger = None
        self.dataset_params = None
        self.train_params = None
        self.model = None
        if "." not in sys.path:
            sys.path.extend(".")

    def parse_params(self, params):
        self.params = deepcopy(params)

        (
            self.train_params,
            self.dataset_params,
            self.dataloader_params,
            self.model_params,
        ) = parse_params(self.params)

    def init(self, params: dict):
        self.seg_trainer = None
        self.parse_params(params)
        (
            self.train_params,
            self.dataset_params,
            self.dataloader_params,
            self.model_params,
        ) = parse_params(params)

        comet_params = self.params.get("logger", {}).get("comet", {})
        comet_information = {
            "apikey": os.getenv("COMET_API_KEY"),
            "project_name": self.params["experiment"]["name"],
            **comet_params,
        }

        self.comet_logger = comet_experiment(comet_information, self.params)
        self.url = self.comet_logger.experiment.url
        self.name = self.comet_logger.experiment.name

        self.train_loader, self.val_loader, self.test_loader = get_dataloaders(
            self.dataset_params, self.dataloader_params
        )
        model_name = self.model_params.pop("name")
        self.model = model_registry[model_name](**self.model_params)

    def launch(self):
        train_and_test(
            self.params,
            self.model,
            self.train_loader,
            self.val_loader,
            self.test_loader,
            self.comet_logger,
            self.train_params,
        )
