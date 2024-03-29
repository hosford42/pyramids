from typing import Tuple, Dict, Optional, Iterator, Union, TYPE_CHECKING

from pyramids import scoring

if TYPE_CHECKING:
    from pyramids import trees


class ParseRule:
    _scoring_features: Dict[Optional[scoring.ScoringFeature], Tuple[float, float, int]]

    def __init__(self, default_score: float = None, default_accuracy: float = None):
        if default_score is None:
            default_score = .5
        if default_accuracy is None:
            default_accuracy = 0.001
        self._scoring_features = {None: (default_score, default_accuracy, 0)}

    # def __str__(self) -> str:
    #     raise NotImplementedError()

    def calculate_weighted_score(self, parse_node: 'trees.TreeNodeInterface') \
            -> Tuple[float, float]:
        default_score, default_weight, count = self._scoring_features[None]
        total_score = default_score * default_weight
        total_weight = default_weight
        for feature in self.iter_scoring_features(parse_node):
            if feature is not None and feature in self._scoring_features:
                score, weight, count = self._scoring_features[feature]
                total_score += score * weight
                total_weight += weight
        return total_score, total_weight

    def adjust_score(self, parse_node: 'trees.TreeNodeInterface', target: float) -> None:
        if not 0 <= target <= 1:
            raise ValueError("Score target must be in the interval [0, 1].")
        default_score, default_weight, count = self._scoring_features[None]
        count += 1
        error = (target - default_score) ** 2
        weight_target = 1 - error
        default_score += (target - default_score) / count
        default_weight += (weight_target - default_weight) / count
        self._scoring_features[None] = (default_score, default_weight, count)
        for feature in self.iter_scoring_features(parse_node):
            if feature in self._scoring_features:
                score, weight, count = self._scoring_features[feature]
                count += 1
            else:
                score, weight, _ = self._scoring_features[None]
                count = 2  # Default is counted as 1, plus one new measurement
            error = (target - score) ** 2
            weight_target = 1 - error
            score += (target - score) / count
            weight += (weight_target - weight) / count
            self._scoring_features[feature] = (score, weight, count)

    def get_score(self, feature: scoring.ScoringFeature) -> Tuple[float, float, int]:
        if feature in self._scoring_features:
            return self._scoring_features[feature]
        else:
            return 0, 0, 0

    def set_score(self, feature: Union[scoring.ScoringKey, scoring.ScoringFeature], score: float,
                  accuracy: float, count: int) -> None:
        if not isinstance(feature, scoring.ScoringFeature):
            feature = scoring.ScoringFeature(feature)
        score = float(score)
        accuracy = float(accuracy)
        if not 0 <= score <= 1:
            raise ValueError("Score must be in the interval [0, 1].")
        if not 0 <= accuracy <= 1:
            raise ValueError("Accuracy must be in the interval [0, 1].")
        if count < 0:
            raise ValueError("Count must be non-negative.")
        # noinspection PyTypeChecker
        self._scoring_features[feature] = (score, accuracy, count)

    def iter_all_scoring_features(self) -> Iterator[Optional[scoring.ScoringFeature]]:
        return iter(self._scoring_features)

    def iter_scoring_features(self, parse_node: 'trees.TreeNodeInterface') \
            -> Iterator[Optional[scoring.ScoringFeature]]:
        raise NotImplementedError()
