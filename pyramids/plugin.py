from typing import Type, Dict

from pyramids.language import Language
from pyramids.loader import ModelLoader
from pyramids.model import Model
from pyramids.tokenization import Tokenizer


class Plugin:

    def __init__(self):
        self._tokenizer_languages = {}
        self._tokenizer_types = {}
        self._model_languages = {}
        self._model_loaders = {}

    def register_tokenizer_type(self, name: str, language: Language,
                                tokenizer_type: Type[Tokenizer]) -> None:
        self._tokenizer_languages[name] = language
        self._tokenizer_types[name] = tokenizer_type

    def register_model(self, name: str, language: Language, model_loader: ModelLoader) -> None:
        self._model_languages[name] = language
        self._model_loaders[name] = model_loader

    @property
    def provided_tokenizer_types(self) -> Dict[str, Language]:
        return self._tokenizer_languages.copy()

    @property
    def provided_models(self) -> Dict[str, Language]:
        return self._model_languages.copy()

    def get_tokenizer_type(self, name: str) -> Type[Tokenizer]:
        return self._tokenizer_types[name]

    def get_model_loader(self, name: str) -> ModelLoader:
        return self._model_loaders[name]

    def load_model(self, name: str) -> Model:
        return self._model_loaders[name].load_model()

    def combine(self, other: 'Plugin') -> 'Plugin':
        result = Plugin()
        for plugin in (self, other):
            result._tokenizer_languages.update(plugin._tokenizer_languages)
            result._tokenizer_types.update(plugin._tokenizer_types)
            result._model_languages.update(plugin._model_languages)
            result._model_loaders.update(plugin._model_loaders)
        return result