# -*- coding: utf-8 -*-

"""
Batchwise parser training and evaluation
"""

from typing import NewType, NamedTuple, Callable, Iterable, Tuple, Optional

from pyramids.sample_utils import SampleSet, Input, Target


__all__ = [
    'Attempt',
    'Result',
    'Failure',
    'Tally',
    'Validator',
    'FeedbackReceiver',
    'AttemptGenerator',
    'ResultCallback',
    'FailureCallback',
    'AttemptFunction',
    'ModelBatchController',
]


Attempt = NewType('Attempt', str)
Result = NamedTuple('Result', [('input', Input), ('attempt', Attempt), ('target', Target), ('score', float)])
Failure = NamedTuple('Failure', [('input', Input), ('target', Target), ('first_attempt', Attempt),
                                 ('attempt_count', int)])
Tally = NamedTuple('Score', [('sample_count', int), ('failure_count', int),
                             ('avg_first_attempt_score', float), ('success_rate', float)])


Validator = Callable[[Attempt, Target], float]
FeedbackReceiver = Callable[[float], None]
AttemptGenerator = Callable[[Input, Target], Iterable[Tuple[Attempt, Optional[FeedbackReceiver]]]]
ResultCallback = Callable[[Result], None]
FailureCallback = Callable[[Failure], None]
AttemptFunction = Callable[[Input], Attempt]


class ModelBatchController:
    """Handles batchwise training and evaluation of models."""

    @staticmethod
    def _default_validator(attempt: Attempt, target: Target):
        return attempt == target

    def __init__(self, output_validator: Validator = None, threshold: float = 1):
        self._validate_output = output_validator or self._default_validator
        self._threshold = threshold

    def run(self, samples: SampleSet, attempt_generator: AttemptGenerator, result_callback: ResultCallback = None,
            failure_callback: FailureCallback = None) -> Tally:
        """Run a set of samples as a batchwise operation."""
        if not samples:
            return Tally(0, 0, 0, 0)
        total = 0
        successes = 0
        for input_val, target in samples.items():
            first = None
            first_score = None
            attempt_count = 0
            success = False
            for output_val, feedback_receiver in attempt_generator(input_val, target):
                attempt_count += 1
                score = self._validate_output(output_val, target)
                if feedback_receiver:
                    feedback_receiver(score)
                if first is None:
                    first = output_val
                    first_score = score
                if score >= self._threshold:
                    success = True
                    successes += 1
                    break
            total += first_score
            if result_callback:
                result_callback(Result(input_val, first, target, first_score))
            if failure_callback and not success:
                failure_callback(Failure(input_val, target, first, attempt_count))
        return Tally(len(samples), len(samples) - successes,  total / len(samples), successes / len(samples))
