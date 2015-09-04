import heapq


__author__ = 'Aaron Hosford'
__all__ = [
    'iter_combinations',
    'PriorityQueue',
    'PrioritySet',
]


def iter_combinations(sequence_list, index=0):
    if index < len(sequence_list):
        for item in sequence_list[index]:
            for tail in iter_combinations(sequence_list, index + 1):
                yield [item] + tail
    else:
        yield []


class PriorityQueue:

    def __init__(self, values=None, key=None):
        self._values = []
        self._key = key
        self._counter = 0
        if values:
            for value in values:
                self.push(value)

    def __len__(self):
        return len(self._values)

    def __bool__(self):
        return bool(self._values)

    def __iter__(self):
        # Does NOT iterate in priority order!
        return iter(self._values)

    def push(self, value):
        # print("Pushing " + repr(value))
        if self._key is None:
            heapq.heappush(self._values, (value, self._counter))
        else:
            heapq.heappush(self._values,
                           (self._key(value), self._counter, value))
        self._counter += 1

    def pop(self):
        if self._key is None:
            value, counter = heapq.heappop(self._values)
        else:
            key, counter, value = heapq.heappop(self._values)
        if not self._values:
            self._counter = 0
        # print("Popping " + repr(value))
        return value


class PrioritySet:
    def __init__(self, values=None, key=None):
        self._queue = PriorityQueue(key=key)
        self._values = set()
        if values is not None:
            for value in values:
                self.push(value)

    def __len__(self):
        return len(self._values)

    def __bool__(self):
        return bool(self._values)

    def __iter__(self):
        # Does NOT iterate in priority order!
        return iter(self._values)

    def push(self, value):
        if value in self._values:
            return
        self._queue.push(value)
        self._values.add(value)

    def pop(self):
        value = self._queue.pop()
        self._values.remove(value)
        return value
