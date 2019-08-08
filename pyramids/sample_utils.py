# -*- coding: utf-8 -*-

"""Utility functions for dealing with samples and sample sets."""

import ast
from typing import Dict, NewType

__author__ = 'Aaron Hosford'
__all__ = [
    'SampleSet',
    'Input',
    'Target',
    'SampleUtils',
]


Input = NewType('Input', str)
Target = NewType('Target', str)
SampleSet = Dict[Input, Target]


class SampleUtils:
    """Utility functions for dealing with samples and sample sets."""

    @staticmethod
    def load(file_path: str) -> SampleSet:
        samples = {}
        for line in open(file_path, 'r'):
            line = line.strip()
            if not line:
                continue
            input_val, output_val = line.split('\t')
            input_val = ast.literal_eval(input_val)
            output_val = ast.literal_eval(output_val)
            samples[Input(input_val)] = Target(output_val)
        return samples

    @staticmethod
    def save(samples: SampleSet, file_path: str) -> None:
        with open(file_path, 'w') as save_file:
            for input_val in sorted(samples):
                save_file.write(repr(str(input_val)) + '\t' + repr(str(samples[input_val])) + '\n')
