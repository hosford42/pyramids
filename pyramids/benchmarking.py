# TODO: Finish this docstring and add docstrings for the rest of the code.
"""
pyramids.benchmarking: Benchmarking of parser accuracy
"""


import pyramids.control

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
                save_file.write(
                    repr(input_val) + '\t' +
                    repr(self._samples[input_val]) + '\n'
                )

    def test(self, function, callback=None):
        for input_val, output_val in self._samples.items():
            output_val = function(input_val)
            if self._samples[input_val] != output_val:
                yield input_val, output_val, self._samples[input_val]
            if callback:
                callback(input_val, output_val, self._samples[input_val])

    def train(self, function, callback=None):
        failures = []
        if not self._samples:
            return failures, 0.0
        for input_val, target in self._samples.items():
            # TODO: Parsing the target & output_val breaks the abstraction of this method.
            #       It was never meant to have insight into the actual content of these
            #       values. Instead of doing this here, allow the caller to pass in
            #       a validator function which is used instead of ordinary equality, and
            #       make ordinary equality the default if no validator is provided. When
            #       the user runs a training session, provide the option to automatically
            #       update benchmarks if they match but not exactly.
            split_index = target.index(':')
            target_category = pyramids.control.ParserLoader.parse_category(target[:split_index])
            target_structure = target[split_index:]
            failed = False
            first = None
            for output_val, feedback_receiver in function(input_val):
                split_index = output_val.index(':')
                output_category = pyramids.control.ParserLoader.parse_category(output_val[:split_index])
                output_structure = output_val[split_index:]
                if first is None:
                    first = output_val
                # if target == output_val:
                if output_category in target_category and target_structure == output_structure:
                    feedback_receiver(True)
                    break
                else:
                    failed = True
                    feedback_receiver(False)
            if failed:
                failures.append((input_val, first, target))
            if callback:
                callback(input_val, first, self._samples[input_val])
        score = (
            (len(self._samples) - len(failures)) /
            float(len(self._samples))
        )
        return failures, score

    def score(self, function, callback=None):
        if not self._samples:
            return 0.0
        failures = 0
        for _ in self.test(function, callback):
            failures += 1
        return (len(self._samples) - failures) / float(len(self._samples))

    def test_and_score(self, function, callback=None):
        failures = []
        if not self._samples:
            return failures, 0.0
        for input_val, output_val, target in self.test(function, callback):
            failures.append((input_val, output_val, target))
        score = (
            (len(self._samples) - len(failures)) /
            float(len(self._samples))
        )
        return failures, score
