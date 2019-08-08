# -*- coding: utf-8 -*-

from typing import Iterable

from sortedcontainers import SortedSet


class WordSetUtils:

    @staticmethod
    def load_word_set(file_path: str) -> SortedSet:
        """Load a word set and return it as a set rule."""
        with open(file_path, encoding='utf-8') as file:
            return SortedSet(line.strip() for line in file)

    @staticmethod
    def save_word_set(file_path: str, words: Iterable[str]) -> None:
        """Load a word set and return it as a set rule."""
        with open(file_path, 'w', encoding='utf-8') as file:
            for word in SortedSet(words):
                file.write(word)
                file.write('\n')
