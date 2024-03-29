# -*- coding: utf-8 -*-

# TODO: This thing is a beast! Refactor.

import cmd
import os
import sys
import time
import traceback
from typing import Optional, List, Iterator, Tuple, Dict

from pyramids.categorization import Category
from pyramids.model import Model
from pyramids.rules.parse_rule import ParseRule

try:
    from graphviz import Digraph
except ImportError:
    Digraph = None

from pyramids.grammar import GrammarParser
from pyramids.trees import Parse, TreeNodeSet, ParseTreeUtils

try:
    # noinspection PyPep8Naming
    import cProfile as profile
except ImportError:
    import profile

from pyramids.batching import Attempt, Result, ModelBatchController, FeedbackReceiver, Failure
from pyramids.config import ModelConfig
from pyramids.loader import ModelLoader
from pyramids.parsing import ParsingAlgorithm
from pyramids.generation import GenerationAlgorithm
from pyramids.sample_utils import Input, Target, SampleSet, SampleUtils

__author__ = 'Aaron Hosford'
__all__ = [
    'ParserCmd',
    'repl',
]


function_to_profile = None


class ParserCmd(cmd.Cmd):

    def __init__(self, model_loader: ModelLoader):
        cmd.Cmd.__init__(self)
        self._model_loader = model_loader
        self._model = model_loader.load_model()
        self.prompt = '% '
        self._simple = True
        self._show_broken = False
        self._parser_state = None
        self._parses = []  # type: List[Parse]
        self._whole_parses = 0
        self._parse_index = 0
        self._fast = False
        self._timeout_interval = 5
        self._emergency_mode = False
        self._benchmark_path = None
        self._benchmark: Optional[SampleSet] = None
        self._benchmark_dirty = False
        self._benchmark_emergency_disambiguations = 0
        self._benchmark_parse_timeouts = 0
        self._benchmark_disambiguation_timeouts = 0
        self._benchmark_time = 0.0
        self._benchmark_tests_completed = 0
        self._benchmark_update_time = time.time()
        self._last_input_text = None
        self.do_load()

    @property
    def model(self) -> Model:
        return self._model

    @property
    def model_loader(self) -> ModelLoader:
        return self._model_loader

    @property
    def max_parse_index(self) -> int:
        if self._show_broken:
            return len(self._parses) - 1 if self._parses else 0
        return self._whole_parses - 1 if self._whole_parses else 0

    @property
    def parses_available(self) -> bool:
        return bool(self._parser_state if self._show_broken else self._whole_parses)

    @property
    def last_input_text(self) -> Optional[str]:
        return self._last_input_text

    def onecmd(self, line: str) -> Optional[bool]:
        # noinspection PyBroadException
        try:
            return cmd.Cmd.onecmd(self, line)
        except Exception:
            traceback.print_exc()

    def precmd(self, line: str) -> str:
        # Pre-processes command lines before they are executed.
        line = line.strip()
        if not line:
            return line
        command = line.split()[0]
        if command == '+':
            return 'good' + line[1:]
        if command == '-':
            return 'bad' + line[1:]
        if command == '++':
            return 'best' + line[2:]
        if command == '--':
            return 'worst' + line[2:]
        return line

    def postcmd(self, stop: Optional[bool], line: str) -> Optional[bool]:
        # Post-processes command results before they are passed back to the
        # command interpreter.
        print('')  # Print a blank line for clarity
        return stop

    def emptyline(self) -> Optional[bool]:
        # Called when the user just hits enter with no input.
        return self.do_next()

    def default(self, line: str) -> Optional[bool]:
        # Called when the command is unrecognized. By default, we assume
        # it's a parse request.
        return self.do_parse(line)

    @staticmethod
    def do_shell(line: str) -> None:
        # Called when the command starts with "!".
        try:
            print(eval(line))
        except SyntaxError:
            exec(line)

    def do_quit(self, line: str) -> Optional[bool]:
        """Save scoring features and exit the parser debugger."""
        if line:
            print("'quit' command does not accept arguments.")
            return
        self.do_save()  # Save what we're doing first.
        return True  # Indicate we're ready to stop.

    def do_exit(self, line: str) -> Optional[bool]:
        """Alias for quit."""
        if line:
            print("'exit' command does not accept arguments.")
            return
        return self.do_quit(line)

    def do_bye(self, line: str) -> Optional[bool]:
        """Alias for quit."""
        if line:
            print("'bye' command does not accept arguments.")
            return
        return self.do_quit(line)

    def do_done(self, line: str) -> Optional[bool]:
        """Alias for quit."""
        if line:
            print("'done' command does not accept arguments.")
            return
        return self.do_quit(line)

    @staticmethod
    def do_cls(_line: str) -> None:
        """Clears the screen."""
        if sys.platform == 'nt':
            os.system('cls')
        else:
            os.system('clear')

    @staticmethod
    def do_clear(_line: str) -> None:
        """Clears the screen."""
        if sys.platform == 'nt':
            os.system('cls')
        else:
            os.system('clear')

    def do_standardize(self, line: str) -> None:
        """Standardizes the parser's files."""
        if not line:
            if self._model and self._model.config_info:
                config_info = self._model.config_info
            else:
                config_info = self._model_loader.load_model_config()
        else:
            config_info = ModelConfig(line)
        self._model_loader.standardize_model(config_info)

    def do_short(self, line: str) -> None:
        """Causes parses to be printed in short form instead of long form."""
        if line:
            print("'short' command does not accept arguments.")
            return
        self._simple = True
        print("Parses will now be printed in short form.")

    def do_broken(self, line: str) -> None:
        """Causes parses that have more pieces or gaps than necessary to be
        listed."""
        if line:
            print("'broken' command does not accept arguments.")
            return
        self._show_broken = True
        print("Parses with more pieces or gaps than necessary will now be listed.")

    def do_whole(self, line: str) -> None:
        """Causes only parses that have no more pieces or gaps than necessary to be listed."""
        if line:
            print("'whole' command does not accept arguments.")
            return
        self._show_broken = False
        self._parse_index = min(self._parse_index, self.max_parse_index)
        print("Only parses with no more pieces or gaps than necessary will now be listed.")

    def do_long(self, line: str) -> None:
        """Causes parses to be printed in long form instead of short form."""
        if line:
            print("'long' command does not accept arguments.")
            return
        self._simple = False
        print("Parses will now be printed in long form.")

    def do_fast(self, line: str) -> None:
        """Causes parsing to stop as soon as a single parse is found."""
        if line:
            print("'fast' command does not accept arguments.")
            return
        self._fast = True
        print("Parsing will now stop as soon as a single parse is found.")

    def do_complete(self, line: str) -> None:
        """Causes parsing to continue until all parses have been identified."""
        if line:
            print("'complete' command does not accept arguments.")
            return
        self._fast = False
        print("Parsing will now continue until all parses have been identified.")

    def do_load(self, line: str = '') -> None:
        """Save scoring features and load a parser from the given configuration file."""
        self.do_save()
        if not line:
            line = self._model.config_info.config_file_path
        if not os.path.isfile(line):
            print("File not found: " + line)
            return
        config_info = ModelConfig(line)
        self._model = self._model_loader.load_model(config_info)
        self._parser_state = None
        self._benchmark = (SampleUtils.load(config_info.benchmark_file)
                           if os.path.isfile(config_info.benchmark_file)
                           else None)
        self._benchmark_dirty = False

    def do_reload(self, line: str = '') -> None:
        """Save scoring features and reload the last configuration file provided."""
        if line:
            print("'reload' command does not accept arguments.")
            return
        self.do_save()
        self.do_load(self._model.config_info.config_file_path
                     if self._model and self._model.config_info
                     else '')

    def do_save(self, line: str = '') -> None:
        """Save scoring features."""
        if line:
            print("'save' command does not accept arguments.")
            return
        if self._model is not None:
            self._model_loader.save_scoring_features(self._model)
            if self._benchmark_dirty:
                SampleUtils.save(self._benchmark, self._model.config_info.benchmark_file)
                self._benchmark_dirty = False

    def do_discard(self, line: str = '') -> None:
        """Discard scoring features."""
        if line:
            print("'discard' command does not accept arguments.")
            return
        self._model_loader.load_scoring_features(self._model)

        config_info = self._model.config_info
        if os.path.isfile(config_info.benchmark_file):
            self._benchmark = SampleUtils.load(config_info.benchmark_file)
        else:
            self._benchmark = None

        self._benchmark_dirty = False

    @staticmethod
    def do_compare(line: str) -> None:
        """Compare two categories to determine if either contains the other."""
        definitions = [definition for definition in line.split() if definition]
        if len(definitions) == 0:
            print("Nothing to compare.")
            return
        if len(definitions) == 1:
            print("Nothing to compare with.")
            return
        categories = set()
        for definition in definitions:
            categories.add(GrammarParser.parse_category(definition,
                                                        offset=line.find(definition) + 1))
        categories = sorted(categories, key=str)
        for category1 in categories:
            for category2 in categories:
                if category1 is not category2:
                    contains_phrase = [" does not contain ", " contains "][category2 in category1]
                    print(str(category1) + contains_phrase + str(category2))

    def do_timeout(self, line: str) -> None:
        """Set (or display) the timeout duration for parsing."""
        if not line:
            print("Parsing timeout duration is currently " + str(self._timeout_interval) +
                  " seconds")
            return
        try:
            try:
                # Only bother with this because an integer looks prettier
                # when printed.
                self._timeout_interval = int(line)
            except ValueError:
                self._timeout_interval = float(line)
        except ValueError:
            print("Timeout duration could not be set to this value.")
        else:
            print("Set parsing timeout duration to " + str(self._timeout_interval) + " seconds.")

    def _do_parse(self, line: str, timeout: float, new_parser_state: bool = True,
                  restriction_category: Category = None, fast: bool = None,
                  emergency: bool = False) -> Tuple[bool, bool, bool]:
        if fast is None:
            fast = self._fast
        if new_parser_state or self._parser_state is None:
            self._parser_state = ParsingAlgorithm.new_parser_state(self._model)
        parse = ParsingAlgorithm.parse(self._parser_state, line, fast, timeout, emergency)
        parse_timed_out = time.time() >= timeout
        emergency_disambiguation = False
        if restriction_category:
            parse = parse.restrict(restriction_category)
        self._parses = [disambiguation
                        for (disambiguation, rank)
                        in parse.get_sorted_disambiguations(None, None, timeout)]
        if not self._parses:
            emergency_disambiguation = True
            self._parses = [parse.disambiguate()]
        disambiguation_timed_out = time.time() >= timeout
        self._whole_parses = len([disambiguation
                                  for disambiguation in self._parses
                                  if ((len(disambiguation.parse_trees)
                                       == len(self._parses[0].parse_trees)) and
                                      (disambiguation.total_gap_size()
                                       == self._parses[0].total_gap_size()))])
        self._parse_index = 0
        self._last_input_text = line
        return emergency_disambiguation, parse_timed_out, disambiguation_timed_out

    def _handle_parse(self, line: str, new_parser_state: bool = True,
                      restriction_category: Category = None, fast: bool = None,
                      emergency: bool = False) -> None:
        """Handle parsing on behalf of do_parse, do_as, and do_extend."""
        if not line:
            print("Nothing to parse.")
            return
        start_time = time.time()
        timeout = start_time + self._timeout_interval
        emergency_disambig, parse_timed_out, disambig_timed_out = \
            self._do_parse(line, timeout, new_parser_state, restriction_category, fast, emergency)
        end_time = time.time()
        print('')
        if parse_timed_out:
            print("*** Parse timed out. ***")
        if disambig_timed_out:
            print("*** Disambiguation timed out. ***")
        if emergency_disambig:
            print("*** Using emergency (non-optimal) disambiguation. ***")
        print('')
        print("Total parse time: " + str(
            round(end_time - start_time, 3)) + " seconds")
        print("Total number of parses: " + str(len(self._parses)))
        print("Total number of whole parses: " + str(self._whole_parses))
        print('')
        self.do_current()

    def do_parse(self, line: str) -> None:
        """Parse an input string and print the highest-scoring parse for it."""
        self._handle_parse(line, emergency=self._emergency_mode)

    def do_as(self, line: str) -> None:
        """Parse an input string as a particular category and print the
        highest-scoring parse for it."""
        if not line:
            print("No category specified.")
            return
        category_definition = line.split()[0]
        category = GrammarParser.parse_category(category_definition)
        line = line[len(category_definition):].strip()
        self._handle_parse(line, restriction_category=category, emergency=self._emergency_mode)

    def do_extend(self, line: str) -> None:
        """Extend the previous input string with additional text and print the
        highest-scoring parse for the combined input strings."""
        self._handle_parse(line, new_parser_state=False, emergency=self._emergency_mode)

    def do_files(self, line: str) -> None:
        """List the word list files containing a given word."""
        if not line:
            print("No word specified.")
            return
        if len(line.split()) > 1:
            print("Expected only one word.")
            return
        word = line.strip()
        config_info = (self._model.config_info
                       if self._model and self._model.config_info
                       else self._model_loader.load_model_config())
        found = False
        for folder_path in config_info.word_sets_folders:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith('.ctg'):
                    continue
                file_path = os.path.join(folder_path, filename)
                with open(file_path) as word_set_file:
                    words = set(word_set_file.read().split())
                if word in words:
                    print(repr(word) + " found in " + file_path + ".")
                    found = True
        if not found:
            print(repr(word) + " not found in any word list files.")

    def do_add(self, line: str) -> None:
        """Adds a word to a given category's word list file."""
        if not line:
            print("No category specified.")
            return
        category_definition = line.split()[0]
        category = GrammarParser.parse_category(category_definition)
        words_to_add = sorted(set(line[len(category_definition):].strip().split()))
        if not words_to_add:
            print("No words specified.")
            return
        config_info = (self._model.config_info
                       if self._model and self._model.config_info
                       else self._model_loader.load_model_config())
        found = False
        for folder_path in config_info.word_sets_folders:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith('.ctg'):
                    continue
                file_category = GrammarParser.parse_category(filename[:-4])
                if file_category != category:
                    continue
                file_path = os.path.join(folder_path, filename)
                with open(file_path) as word_set_file:
                    words = set(word_set_file.read().split())
                for w in words_to_add:
                    if w in words:
                        print(repr(w) + " was already in " + file_path + ".")
                    else:
                        print("Adding " + repr(w) + " to " + file_path + ".")
                        words.add(w)
                with open(file_path, 'w') as word_set_file:
                    word_set_file.write('\n'.join(sorted(words)))
                found = True
        if not found:
            for folder_path in config_info.word_sets_folders:
                file_path = os.path.join(folder_path, str(category) + '.ctg')
                print("Creating " + file_path + ".")
                with open(file_path, 'w') as word_set_file:
                    word_set_file.write('\n'.join(sorted(words_to_add)))
                break
            else:
                print("No word sets folder identified. Cannot add words.")
                return
        self.do_reload()

    def do_remove(self, line: str) -> None:
        """Removes a word from a given category's word list file."""
        if not line:
            print("No category specified.")
            return
        category_definition = line.split()[0]
        words_to_remove = set(line[len(category_definition):].strip().split())
        if not words_to_remove:
            print("No words specified.")
            return
        category = GrammarParser.parse_category(category_definition)
        config_info = (self._model.config_info
                       if self._model and self._model.config_info
                       else self._model_loader.load_model_config())
        found = set()
        for folder_path in config_info.word_sets_folders:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith('.ctg'):
                    continue
                file_category = GrammarParser.parse_category(filename[:-4])
                if file_category != category:
                    continue
                file_path = os.path.join(folder_path, filename)
                with open(file_path) as words_file:
                    words = set(words_file.read().split())
                for w in sorted(words_to_remove):
                    if w in words:
                        print("Removing " + repr(w) + " from " + file_path + ".")
                        words.remove(w)
                        found.add(w)
                    else:
                        print(repr(w) + " not found in " + file_path + ".")
                if words:
                    with open(file_path, 'w') as words_file:
                        words_file.write('\n'.join(sorted(words)))
                else:
                    print("Deleting empty word list file " + file_path + ".")
                    os.remove(file_path)
        if words_to_remove - found:
            print("No file(s) found containing the following words: " +
                  ' '.join(repr(word) for word in sorted(words_to_remove - found)) + ".")
            return
        self.do_reload()

    def do_profile(self, line: str) -> None:
        """Profiles the execution of a command, printing the profile statistics."""

        # Only a function at the module level can be profiled. To get
        # around this limitation, we define a temporary module-level
        # function that calls the method we want to profile.
        global function_to_profile

        def _function_to_profile():
            self.onecmd(line)

        function_to_profile = _function_to_profile

        profile.run('function_to_profile()')

    def do_analyze(self, line: str) -> None:
        """Analyzes the last parse and prints statistics useful for debugging."""
        if line:
            print("'analyze' command does not accept arguments.")
            return
        if self._parser_state is None:
            print("Nothing to analyze.")
            return

        print('Covered: ' + repr(self._parser_state.is_covered()))
        rule_counts, rule_nodes = self._get_rule_map()
        counter = 0
        for rule in sorted(rule_counts, key=rule_counts.get, reverse=True):
            print(str(rule) + " (" + str(rule_counts[rule]) + " nodes)")
            for node_str in sorted(ParseTreeUtils.to_str(node, simplify=True)
                                   for node in rule_nodes[rule]):
                print('    ' + node_str.replace('\n', '\n    '))
                counter += node_str.count('\n') + 1
            if counter >= 100:
                break
        print("Rules in waiting:")
        rule_counts = {}
        for node in self._parser_state.insertion_queue:
            rule_counts[node.rule] = rule_counts.get(node.rule, 0) + 1
        for rule in sorted(rule_counts, key=rule_counts.get, reverse=True):
            print(str(rule) + " (" + str(rule_counts[rule]) + " nodes)")

    def _get_rule_map(self) -> Tuple[Dict[ParseRule, int],
                                     Dict[ParseRule, List[TreeNodeSet]]]:
        """Collect and count the nodes, organized by rule, from the latest parse's category map."""
        cat_map = self._parser_state.category_map
        rule_counts = {}
        rule_nodes = {}
        for start, category, end in cat_map:
            for node_set in cat_map.iter_node_sets(start, category, end):
                for node in node_set:
                    rule_counts[node.rule] = rule_counts.get(node.rule, 0) + 1
                    rule_nodes[node.rule] = rule_nodes.get(node.rule, []) + [node]
        return rule_counts, rule_nodes

    def do_links(self, line: str) -> None:
        """Display the semantic net links for the current parse."""
        if line:
            print("'links' command does not accept arguments.")
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            for sentence in parse.get_parse_graphs():
                print(sentence)
                print('')
        else:
            print("No parses found.")

    def do_reverse(self, line: str) -> None:
        """Display token sequences that produce the same semantic net links as the current parse."""
        if line:
            print("'reverse' command does not accept arguments.")
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            start_time = time.time()
            sentences = list(parse.get_parse_graphs())
            results = [GenerationAlgorithm().generate(self._model, sentence)
                       for sentence in sentences]
            end_time = time.time()
            for sentence, result in zip(sentences, results):
                print(sentence)
                print('')
                for tree in sorted(result, key=lambda t: t.tokens):
                    text = ' '.join(tree.tokens)
                    text = text[:1].upper() + text[1:]
                    for punctuation in ',.?!:;)]}':
                        text = text.replace(' ' + punctuation, punctuation)
                    for punctuation in '([{':
                        text = text.replace(punctuation + ' ', punctuation)
                    print('"' + text + '"')
                    print(tree)
                    print('')
                print('')
                print("Total time: " + str(end_time - start_time) + " seconds")
                print('')
        else:
            print("No parses found.")

    def do_current(self, line: str = '') -> None:
        """Reprint the current parse for the most recent input string."""
        if line:
            print("'current' command does not accept arguments.")
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            gaps = parse.total_gap_size()
            size = len(parse.parse_trees)
            score, confidence = parse.get_weighted_score()
            print("Parses #" + str(self._parse_index + 1) + " of " +
                  str(self.max_parse_index + 1) + ":")
            print(parse.to_str(self._simple))
            print("Gaps: " + str(gaps))
            print("Size: " + str(size))
            print("Score: " + str(score))
            print("Confidence: " + str(confidence))
            print("Coverage: " + str(parse.coverage))
        else:
            print("No parses found.")

    def do_next(self, line: str = '') -> None:
        """Print the next parse for the most recent input string."""
        if line:
            print("'next' command does not accept arguments.")
            return
        if self.parses_available:
            if self._parse_index >= self.max_parse_index:
                print("No more parses available.")
                return
            self._parse_index += 1
        self.do_current()

    def do_previous(self, line: str) -> None:
        """Print the previous parse for the most recent input string."""
        if line:
            print("'next' command does not accept arguments.")
            return
        if self.parses_available:
            if self._parse_index <= 0:
                print("No more parses available.")
                return
            self._parse_index -= 1
        self.do_current()

    def do_first(self, line: str) -> None:
        """Print the first parse for the most recent input string."""
        if line:
            print("'first' command does not accept arguments.")
            return
        self._parse_index = 0
        self.do_current()

    def do_last(self, line: str) -> None:
        """Print the last parse for the most recent input string."""
        if line:
            print("'last' command does not accept arguments.")
            return
        self._parse_index = self.max_parse_index
        self.do_current()

    def do_show(self, line: str) -> None:
        """Print the requested parse for the most recent input string."""
        if len(line.split()) != 1:
            print("'show' command requires a single integer argument.")
            return
        try:
            index = int(line.strip())
        except ValueError:
            print("'show' command requires a single integer argument.")
            return
        if not (index and (-(self.parses_available + 1) <= index <= self.parses_available + 1)):
            print("Index out of range.")
            return
        if index < 0:
            index += self.parses_available + 1
        else:
            index -= 1
        self._parse_index = index
        self.do_current()

    def do_gaps(self, line: str) -> None:
        """Print the gaps in the current parse."""
        if line:
            print("'gaps' command does not accept arguments.")
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            print("Gaps: " + str(parse.total_gap_size()))
            for start, end in parse.iter_gaps():
                print('  ' + str(start) + ' to ' + str(end) + ': ' +
                      ' '.join(parse.tokens[start:end]))
        else:
            print("No parses found.")

    def do_best(self, line: str) -> None:
        """Adjust the score upward for the most recently printed parse until it
        is higher than all others returned."""
        if line:
            print("'best' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available for adjustment.")
            return
        best_parse = self._parses[self._parse_index]
        for _ in range(100):
            self._parses[self._parse_index].adjust_score(True)
            ranks = {}
            for parse in self._parses:
                ranks[parse] = parse.get_rank()
            self._parses.sort(key=ranks.get, reverse=True)
            self._parse_index = [id(parse) for parse in self._parses].index(id(best_parse))
            if (self._parses[0] is best_parse or
                    (len(self._parses[self._parse_index - 1].parse_trees)
                     != len(best_parse.parse_trees)) or
                    (self._parses[self._parse_index - 1].total_gap_size()
                     != best_parse.total_gap_size())):
                break
        if self._parse_index == 0:
            print("Successfully made this parse the highest ranked.")
        else:
            print("Failed to make this parse the highest ranked.")

    def do_worst(self, line: str) -> None:
        """Adjust the score downward for the most recently printed parse until
        it is lower than all others returned."""
        if line:
            print("'worst' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available for adjustment.")
            return
        worst_parse = self._parses[self._parse_index]
        for _ in range(100):
            self._parses[self._parse_index].adjust_score(False)
            ranks = {}
            for parse in self._parses:
                ranks[parse] = parse.get_rank()
            self._parses.sort(key=ranks.get, reverse=True)
            self._parse_index = [id(parse) for parse in self._parses].index(id(worst_parse))
            if (self._parses[-1] is worst_parse or
                    (len(self._parses[self._parse_index + 1].parse_trees)
                     != len(worst_parse.parse_trees)) or
                    (self._parses[self._parse_index + 1].total_gap_size()
                     != worst_parse.total_gap_size())):
                break
        if self._parse_index == self.max_parse_index:
            print("Successfully made this parse the lowest ranked.")
        else:
            print("Failed to make this parse the lowest ranked.")

    def do_good(self, line: str) -> None:
        """Adjust the score upward for the most recently printed parse."""
        if line:
            print("'next' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available for adjustment.")
            return
        self._parses[self._parse_index].adjust_score(True)

    def do_bad(self, line: str) -> None:
        """Adjust the score downward for the most recently printed parse."""
        if line:
            print("'next' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available for adjustment.")
            return
        self._parses[self._parse_index].adjust_score(False)

    def _get_benchmark_parser_output(self) -> str:
        parse = self._parses[self._parse_index]
        result = set()
        for sentence in parse.get_parse_graphs():
            result.add(str(sentence))
        return '\n'.join(sorted(result))

    def do_keep(self, line: str) -> None:
        """Save the current parse as benchmark case."""
        if line:
            print("'keep' command does not accept arguments.")
            return
        if not self._parses:
            print("No parses available.")
            return
        assert self._benchmark is not None
        self._benchmark[Input(self.last_input_text)] = Target(self._get_benchmark_parser_output())
        self._benchmark_dirty = True

    # noinspection PyUnusedLocal
    def _test_attempt_iterator(self, text: Input, target: Target) -> Iterator[Tuple[Attempt, None]]:
        start_time = time.time()
        emergency_disambig, parse_timed_out, disambig_timed_out = \
            self._do_parse(text, start_time + self._timeout_interval)
        end_time = time.time()
        self._benchmark_emergency_disambiguations += int(emergency_disambig)
        self._benchmark_parse_timeouts += int(parse_timed_out)
        self._benchmark_disambiguation_timeouts += int(disambig_timed_out)
        self._benchmark_time += end_time - start_time
        yield Attempt(self._get_benchmark_parser_output()), None

    # noinspection PyUnusedLocal
    def _report_benchmark_progress(self, result: Result) -> None:
        assert self._benchmark is not None

        self._benchmark_tests_completed += 1
        if time.time() >= self._benchmark_update_time + 1:
            print("Benchmark " +
                  str(round((100 * self._benchmark_tests_completed / float(len(self._benchmark))),
                            ndigits=1)) +
                  "% complete...")
            self._benchmark_update_time = time.time()

    def do_benchmark(self, line: str) -> None:
        """Parse all benchmark samples and report statistics on them as a batch."""
        if line:
            print("'benchmark' command does not accept arguments.")
            return
        if not self._benchmark:
            print("No benchmarking samples.")
            return
        self._benchmark_emergency_disambiguations = 0
        self._benchmark_parse_timeouts = 0
        self._benchmark_disambiguation_timeouts = 0
        self._benchmark_time = 0.0
        self._benchmark_tests_completed = 0
        self._benchmark_update_time = time.time()
        failures = []  # type: List[Failure]
        tally = ModelBatchController(self._validate_output)\
            .run_batch(self._benchmark, self._test_attempt_iterator,
                       self._report_benchmark_progress, failures.append)
        print("")
        if failures:
            print('')
            print("Failures:")
            for failure in failures:
                print(failure.input)
                print(failure.first_attempt)
                print(failure.target)
                print('')
        print("Score: " + str(round(100 * tally.avg_first_attempt_score, 1)) + "%")
        print("Average Parse Time: " + str(round(self._benchmark_time / float(len(self._benchmark)),
                                                 ndigits=1)) +
              ' seconds per parse')
        print("Samples Evaluated: " + str(len(self._benchmark)))
        print("Emergency Disambiguations: " + str(self._benchmark_emergency_disambiguations) +
              " (" + str(round(100 * self._benchmark_emergency_disambiguations
                               / float(len(self._benchmark)), ndigits=1)) + '%)')
        print("Parse Timeouts: " + str(self._benchmark_parse_timeouts) + " (" +
              str(round(100 * self._benchmark_parse_timeouts / float(len(self._benchmark)),
                        ndigits=1)) + '%)')
        print("Disambiguation Timeouts: " + str(self._benchmark_disambiguation_timeouts) + " (" +
              str(round(100 * self._benchmark_disambiguation_timeouts / float(len(self._benchmark)),
                        ndigits=1)) + '%)')

    def _scoring_function(self, target: float) -> None:
        # NOTE: It is important that positive reinforcement not
        #       occur if the first try gives the right answer and
        #       the score is already >= .9; otherwise, it will
        #       throw off the relative scoring of other parses.
        if (not target or self._parse_index or
                self._parses[self._parse_index].get_weighted_score()[0] < .9):
            self._parses[self._parse_index].adjust_score(target)

    def _training_attempt_iterator(self, text: Input,
                                   target: Target) -> Iterator[Tuple[Attempt, FeedbackReceiver]]:
        print(text)

        # Restrict it to the correct category and token_start_index from there. This gives the
        # parser a leg up when it's far from the correct response.
        split_index = target.index(':')
        target_category = GrammarParser.parse_category(target[:split_index])
        start_time = time.time()
        end_time = start_time + self._timeout_interval
        emergency_disambig, parse_timed_out, disambig_timed_out = \
            self._do_parse(text, end_time, restriction_category=target_category)
        end_time = time.time()
        self._benchmark_emergency_disambiguations += int(emergency_disambig)
        self._benchmark_parse_timeouts += int(parse_timed_out)
        self._benchmark_disambiguation_timeouts += int(disambig_timed_out)
        self._benchmark_time += end_time - start_time

        # We shouldn't keep going if there are no parses of the correct category. This most likely
        # indicates a change in the grammar, not a problem with the model.
        assert self.parses_available
        while self._parse_index <= self.max_parse_index:
            # (benchmark target, scoring function)
            yield self._get_benchmark_parser_output(), self._scoring_function
            self._parse_index += 1

        # Now try it without any help,
        start_time = time.time()
        end_time = start_time + self._timeout_interval
        emergency_disambig, parse_timed_out, disambig_timed_out = self._do_parse(text, end_time)
        end_time = time.time()
        self._benchmark_emergency_disambiguations += int(emergency_disambig)
        self._benchmark_parse_timeouts += int(parse_timed_out)
        self._benchmark_disambiguation_timeouts += int(disambig_timed_out)
        self._benchmark_time += end_time - start_time
        if self.parses_available:
            while self._parse_index <= self.max_parse_index:
                # (benchmark target, scoring function)
                yield self._get_benchmark_parser_output(), self._scoring_function
                self._parse_index += 1

    @staticmethod
    def _validate_output(output_val: str, target: str) -> bool:
        if ':' not in output_val:
            return False
        split_index = target.index(':')
        target_category = GrammarParser.parse_category(target[:split_index])
        target_structure = target[split_index:]
        split_index = output_val.index(':')
        output_category = GrammarParser.parse_category(output_val[:split_index])
        output_structure = output_val[split_index:]
        return output_category in target_category and target_structure == output_structure

    def do_train(self, line: str) -> None:
        """Automatically adjust scoring to improve benchmark statistics."""
        if line:
            print("'train' command does not accept arguments.")
            return
        if not self._benchmark:
            print("No benchmarking samples.")
            return
        self._benchmark_emergency_disambiguations = 0
        self._benchmark_parse_timeouts = 0
        self._benchmark_disambiguation_timeouts = 0
        self._benchmark_time = 0.0
        self._benchmark_tests_completed = 0
        self._benchmark_update_time = time.time()
        failures = []  # type: List[Failure]
        tally = ModelBatchController(self._validate_output)\
            .run_batch(self._benchmark, self._training_attempt_iterator,
                       self._report_benchmark_progress, failures.append)
        print("")
        if failures:
            print('')
            print("Failures:")
            for failure in failures:
                print(failure.input)
                print(failure.first_attempt)
                print(failure.target)
                print('')
        print("Score: " + str(round(100 * tally.avg_first_attempt_score, 1)) + "%")
        print("Average Parse Time: " + str(round(self._benchmark_time / float(len(self._benchmark)),
                                                 ndigits=1)) +
              ' seconds per parse')
        print("Samples Evaluated: " + str(len(self._benchmark)))
        print("Emergency Disambiguations: " + str(self._benchmark_emergency_disambiguations) +
              " (" + str(round(100 * self._benchmark_emergency_disambiguations
                               / float(len(self._benchmark)), ndigits=1)) + '%)')
        print("Parse Timeouts: " + str(self._benchmark_parse_timeouts) + " (" +
              str(round(100 * self._benchmark_parse_timeouts / float(len(self._benchmark)),
                        ndigits=1)) + '%)')
        print("Disambiguation Timeouts: " + str(self._benchmark_disambiguation_timeouts) + " (" +
              str(round(100 * self._benchmark_disambiguation_timeouts / float(len(self._benchmark)),
                        ndigits=1)) + '%)')

    def do_training(self, line: str) -> None:
        """Repeatedly train and save until user hits Ctrl-C."""
        if line:
            print("'training' command does not accept arguments.")
            return
        if not self._benchmark:
            print("No benchmarking samples.")
            return
        iteration = 0
        while True:
            try:
                iteration += 1
                print("Iteration:", iteration)
                self.do_train('')
                self.do_save('')
            except KeyboardInterrupt:
                self.do_save('')
                break

    def do_list(self, line: str) -> None:
        """List all benchmark samples."""
        if line:
            print("'list' command does not accept arguments.")
            return
        if not self._benchmark:
            print("No benchmarking samples.")
            return
        print(str(len(self._benchmark)) + " recorded benchmark samples:")
        max_tokens = 0
        total_tokens = 0
        for input_val in sorted(self._benchmark):
            print("  " + input_val)
            count = len(list(self._model.tokenizer.tokenize(input_val)))
            total_tokens += count
            if count > max_tokens:
                max_tokens = count
        print('')
        print("Longest benchmark sample: " + str(max_tokens) + " tokens")
        print("Average benchmark sample length: " +
              str(round(total_tokens / float(len(self._benchmark)), ndigits=1)) + " tokens")

    def do_visualize(self, line: str) -> None:
        """Visualize the most recent parse."""
        if line:
            print("'visualize' command does not accept arguments.")
            return
        if Digraph is None:
            print('The graphviz library is not installed.')
            return
        if self.parses_available:
            parse = self._parses[self._parse_index]
            gv_graph = Digraph()
            for graph in parse.get_parse_graphs():
                with gv_graph.subgraph() as subgraph:
                    graph.visualize(subgraph)
            gv_graph.view()
        else:
            print("No parses found.")

    def do_emergency(self, line: str) -> None:
        """Set, clear, or display the emergency parsing mode flag."""
        line = line.strip()
        if line == 'on':
            self._emergency_mode = True
            print("Emergency mode is on.")
        elif line == 'off':
            self._emergency_mode = False
            print("Emergency mode is off.")
        elif not line:
            print('Emergency mode is %s.' % ('on' if self._emergency_mode else 'off'))
        else:
            print('Unexpected argument: ' + line)


def repl(model_loader: ModelLoader) -> None:
    """Run the interactive command line interface to the parser."""
    parser_cmd = ParserCmd(model_loader)
    print('')
    parser_cmd.cmdloop()
