import os
import importlib
from inspect import signature
import torch
from ruamel.yaml import YAML, comments
from io import StringIO
from typing import Any, Mapping


def get_module_class_from_path(path):
    path = os.path.normpath(path)
    splitted = path.split(os.sep)
    module = ".".join(splitted[:-1])
    cls = splitted[-1]
    return module, cls


def instantiate_class(name, params):
    module, cls = get_module_class_from_path(name)
    imp_module = importlib.import_module(module)
    imp_cls = getattr(imp_module, cls)
    if (
        len(signature(imp_cls).parameters.keys()) == 1
        and "params" in list(signature(imp_cls).parameters.keys())[0]
    ):
        return imp_cls(params)
    return imp_cls(**params)


def substitute_values(x: torch.Tensor, values, unique=None):
    """
    Substitute values in a tensor with the given values
    :param x: the tensor
    :param unique: the unique values to substitute
    :param values: the values to substitute with
    :return: the tensor with the values substituted
    """
    if unique is None:
        unique = x.unique()
    lt = torch.full((unique.max() + 1,), -1, dtype=values.dtype, device=x.device)
    lt[unique] = values
    return lt[x]


def load_yaml(path, return_string=False):
    if hasattr(path, "readlines"):
        d = convert_commentedmap_to_dict(YAML().load(path))
        if return_string:
            path.seek(0)
            return d, path.read().decode("utf-8")
    with open(path, "r") as param_stream:
        d = convert_commentedmap_to_dict(YAML().load(param_stream))
        if return_string:
            param_stream.seek(0)
            return d, str(param_stream.read())
    return d


def convert_commentedmap_to_dict(data):
    """
    Recursive function to convert CommentedMap to dict
    """
    if isinstance(data, comments.CommentedMap):
        result = {}
        for key, value in data.items():
            result[key] = convert_commentedmap_to_dict(value)
        return result
    elif isinstance(data, list):
        return [convert_commentedmap_to_dict(item) for item in data]
    else:
        return data


def log_every_n(batch_idx: int, n: int):
    if batch_idx % n == 0:
        return True
    else:
        return False


def dict_to_yaml_string(mapping: Mapping) -> str:
    """
    Convert a nested dictionary or list to a string
    """
    string_stream = StringIO()
    yaml = YAML()
    yaml.dump(mapping, string_stream)
    output_str = string_stream.getvalue()
    string_stream.close()
    return output_str


def get_checkpoints_dir_path(
    project_name: str, group_name: str, ckpt_root_dir: str = None
):
    """Creating the checkpoint directory of a given experiment.
    :param experiment_name:     Name of the experiment.
    :param ckpt_root_dir:       Local root directory path where all experiment logging directories will
                                reside. When none is give, it is assumed that pkg_resources.resource_filename('checkpoints', "")
                                exists and will be used.
    :return:                    checkpoints_dir_path
    """
    if ckpt_root_dir:
        return os.path.join(ckpt_root_dir, project_name, group_name)
