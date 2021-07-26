# TODO: Create a registry for officially-supported models. Allow these to be automatically installed
#       on request, instead of having to use pip.
# TODO: Make the annotator app consult the plugins to choose a parser model before annotating
#       begins.
# TODO: Make the repl package allow switching between parser models from the command line instead of
#       requiring a model loader as a parameter. (Keep it as an optional parameter, though.)
import logging
from typing import Type, Set, NamedTuple

import pkg_resources

from pyramids.config import ModelConfig
from pyramids.loader import ModelLoader
from pyramids.model import Model
from pyramids.plugin import Plugin
from pyramids.tokenization import Tokenizer

__all__ = [
    'PLUGIN_ENTRY_POINT',
    'get_available_tokenizers',
    'get_available_models',
    'get_tokenizer',
    'get_model_loader',
    'load_model',
]

PluginEntry = NamedTuple('PluginEntry', [('provider', str), ('name', str)])

PLUGIN_ENTRY_POINT = 'pyramids.plugins'

LOGGER = logging.getLogger(__name__)


def get_available_tokenizers(language_name: str = None, iso639_1: str = None,
                             iso639_2: str = None) -> Set[PluginEntry]:
    results = set()
    for plugin_name in _PLUGINS:
        plugin: Plugin = _PLUGINS[plugin_name]
        for name, language in plugin.provided_tokenizer_types.items():
            if language_name is not None and language.name != language_name:
                continue
            if iso639_1 is not None and language.iso639_1 != iso639_1:
                continue
            if iso639_2 is not None and language.iso639_2 != iso639_2:
                continue
            results.add(PluginEntry(plugin_name, name))
    return results


def get_available_models(language_name: str = None, iso639_1: str = None,
                         iso639_2: str = None) -> Set[PluginEntry]:
    results = set()
    for plugin_name in _PLUGINS:
        plugin: Plugin = _PLUGINS[plugin_name]
        for name, language in plugin.provided_models.items():
            if language_name is not None and language.name != language_name:
                continue
            if iso639_1 is not None and language.iso639_1 != iso639_1:
                continue
            if iso639_2 is not None and language.iso639_2 != iso639_2:
                continue
            results.add(PluginEntry(plugin_name, name))
    return results


def get_tokenizer(plugin_name: str, tokenizer_name: str,
                  config_info: ModelConfig = None) -> Tokenizer:
    plugin: Plugin = _PLUGINS[plugin_name]
    tokenizer_type: Type[Tokenizer] = plugin.get_tokenizer_type(tokenizer_name)
    if config_info is None:
        return tokenizer_type()
    else:
        return tokenizer_type.from_config(config_info)


def get_model_loader(plugin_name: str, model_name: str) -> ModelLoader:
    """Return a model loader from the plugin registry."""
    plugin: Plugin = _PLUGINS[plugin_name]
    return plugin.get_model_loader(model_name)


def load_model(plugin_name: str, model_name: str) -> Model:
    """Load a model from the plugin registry."""
    plugin: Plugin = _PLUGINS[plugin_name]
    return plugin.load_model(model_name)


def _load_plugins():
    plugins = {}
    for entry_point in pkg_resources.iter_entry_points(PLUGIN_ENTRY_POINT):
        name = entry_point.name
        # noinspection PyBroadException
        try:
            plugin = entry_point.load()
        except Exception:
            LOGGER.exception("Plugin '%s' ignored due to exception while loading:", name)
            continue
        if not isinstance(plugin, Plugin):
            LOGGER.error("Plugin '%s' ignored due to unexpected type.", name)
            continue
        if name in plugins:
            plugins[name] = plugins[name].combine(plugin)
        else:
            plugins[name] = plugin
    return plugins


_PLUGINS = _load_plugins()
