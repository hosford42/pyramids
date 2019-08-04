# TODO: Finish this docstring and add docstrings for the rest of the code.
"""
pyramids.benchmarking: Benchmarking of parser accuracy
"""

__author__ = 'Aaron Hosford'
__all__ = [
    'Benchmark',
]


class Benchmark:

    @classmethod
    def load(cls, file_path):
        samples = {}
        for line in open(file_path, 'r'):
            line = line.strip()
            if not line:
                continue
            input_val, output_val = line.split('\t')
            input_val = eval(input_val)
            output_val = eval(output_val)
            samples[input_val] = output_val
        return cls(samples)

    def __init__(self, samples=None):
        self._samples = dict(samples) if samples else {}

    @property
    def samples(self):
        return self._samples

    def save(self, file_path):
        with open(file_path, 'w') as save_file:
            for input_val in sorted(self._samples):
                save_file.write(repr(input_val) + '\t' + repr(self._samples[input_val]) + '\n')

    @staticmethod
    def _default_validator(output_val, target):
        return output_val == target

    def test(self, function, output_validator=None, callback=None):
        output_validator = output_validator or self._default_validator
        for input_val, target in self._samples.items():
            output_val = function(input_val)
            if output_validator(output_val, target):
                yield input_val, output_val, target
            if callback:
                callback(input_val, output_val, target)

    def train(self, attempt_iterator, output_validator=None, callback=None):
        output_validator = output_validator or self._default_validator
        failures = []
        if not self._samples:
            return failures, 0.0
        for input_val, target in self._samples.items():
            # TODO: When the user runs a training session, provide the option to automatically update benchmarks if
            #       they match but not exactly.
            failed = False
            first = None
            for output_val, feedback_receiver in attempt_iterator(input_val, target):
                if first is None:
                    first = output_val
                if output_validator(output_val, target):
                    feedback_receiver(True)
                    break
                else:
                    failed = True
                    feedback_receiver(False)
            if failed:
                failures.append((input_val, first, target))
            if callback:
                callback(input_val, first, self._samples[input_val])
        score = (len(self._samples) - len(failures)) / len(self._samples)
        return failures, score

    def score(self, function, output_validator=None, callback=None):
        output_validator = output_validator or self._default_validator
        if not self._samples:
            return 0.0
        failures = 0
        for _ in self.test(function, output_validator, callback):
            failures += 1
        return (len(self._samples) - failures) / float(len(self._samples))

    def test_and_score(self, function, output_validator=None, callback=None):
        output_validator = output_validator or self._default_validator
        failures = []
        if not self._samples:
            return failures, 0.0
        for input_val, output_val, target in self.test(function, output_validator, callback):
            failures.append((input_val, output_val, target))
        score = (len(self._samples) - len(failures)) / float(len(self._samples))
        return failures, score
