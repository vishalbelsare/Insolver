import os
import sys
import json
import pickle
import importlib
import warnings
import dill

from insolver.frame import InsolverDataFrame
from insolver.transforms import basic, person, insurance, autofillna, date_time, grouping_sorting


class InsolverTransform(InsolverDataFrame):
    """Class to compose transforms to be done on InsolverDataFrame. Transforms may have the priority param.
    Priority=0: transforms which get values from other (TransformAgeGetFromBirthday, TransformRegionGetFromKladr, etc).
    Priority=1: main transforms of values (TransformAge, TransformVehPower, etc).
    Priority=2: transforms which get intersections of features (TransformAgeGender, etc);
    transforms which sort values (TransformParamSortFreq, TransformParamSortAC).
    Priority=3: transforms which get functions of values (TransformPolynomizer, TransformGetDummies, etc).

    Parameters:
        df: InsolverDataFrame to transform.
        transforms: List of transforms to be done.
    """
    _metadata = ['transforms', 'transforms_done']

    def __init__(self, df, transforms):
        super().__init__(df)
        if isinstance(transforms, list):
            self.transforms = transforms
        self.transforms_done = dict()

    def ins_transform(self):
        """Transforms data in InsolverDataFrame.

        Returns:
            list: List of transforms have been done.
        """
        if self.transforms:

            priority = 0
            for transform in self.transforms:
                if hasattr(transform, 'priority'):
                    if transform.priority < priority:
                        warnings.warn('WARNING! Check the order of transforms. '
                                      'Transforms with higher priority should be done first.', stacklevel=0)
                        break
                    else:
                        priority = transform.priority

            for n, transform in enumerate(self.transforms):
                self._update_inplace(transform(self))
                attributes = dict()
                for attribute in dir(transform):
                    if not attribute.startswith('_'):
                        attributes.update({attribute: getattr(transform, attribute)})
                self.transforms_done.update({n: {'name': type(transform).__name__, 'attributes': attributes}})

        return self.transforms_done

    def save(self, filename):
        with open(filename, 'wb') as file:
            pickle.dump(self.transforms_done, file)

    def save2(self, filename):
        with open(filename, 'wb') as file:
            dill.dump(self.transforms, file)

    def save_json(self, filename):
        with open(filename, 'w') as file:
            json.dump(self.transforms_done, file, separators=(',', ':'), sort_keys=True, indent=4)


def load_class(module_list, transform_name):
    for module in module_list:
        try:
            transform_class = getattr(module, transform_name)
            return transform_class
        except AttributeError:
            pass


def load_transforms(path):
    with open(path, 'rb') as file:
        return dill.load(file)


def init_transforms(transforms, module_path=None, inference=False):
    """Function for creation transformations objects from the dictionary.

    Args:
        transforms (list): Dictionary with classes and their init parameters.
        module_path (str, None): Path to the user transformations saved in .py file. E.g., user_transforms.py.
        inference (bool): Should be 'False' if transforms are applied while preparing data for modeling.
            Should be 'True' if transforms are applied on inference.

    Returns:
        list: List of transformations objects.
    """
    transforms_list = []
    module_list = [basic, person, insurance, autofillna, date_time, grouping_sorting]

    if not ((module_path is None) or (module_path == '')):
        _directory = os.path.dirname(os.path.abspath(module_path))
        _script = os.path.basename(os.path.abspath(module_path))
        if not _script.endswith('.py'):
            raise ValueError('Argument module_path should contain path to the .py file.')
        else:
            user_transforms = _script.strip('.py')
        sys.path.insert(1, _directory)

        try:
            user_transforms = importlib.import_module(user_transforms)
            importlib.reload(user_transforms)
            module_list.append(user_transforms)

        except ModuleNotFoundError:
            pass

    for n in transforms:
        try:
            del transforms[n]['attributes']['priority']
        except KeyError:
            pass

        if inference in transforms[n]['attributes'].keys():
            transforms[n]['attributes']['inference'] = inference

        transform_class = load_class(module_list, transforms[n]['name'])
        if transform_class:
            transforms_list.append(transform_class(**transforms[n]['attributes']))

    return transforms_list


def import_transforms(module_path):
    """Function for importing custom transformations into dictionary.

        Args:
            module_path (str): Path to the user transformations saved in .py file. E.g., user_transforms.py.

        Returns:
            dict: Dictionary containing user-defined transformations.
        """
    if not module_path == '':
        _directory = os.path.dirname(os.path.abspath(module_path))
        _script = os.path.basename(os.path.abspath(module_path))
        if not _script.endswith('.py'):
            raise ValueError('Argument module_path should contain path to the .py file.')
        else:
            user_transforms = _script.strip('.py')
        sys.path.insert(1, _directory)

        user_transforms = importlib.import_module(user_transforms)
        importlib.reload(user_transforms)

        if "__all__" in user_transforms.__dict__:
            names = user_transforms.__dict__["__all__"]
        else:
            names = [x for x in user_transforms.__dict__ if not x.startswith("_")]
        return {k: getattr(user_transforms, k) for k in names}
