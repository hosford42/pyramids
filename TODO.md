# Urgent

Before the next release:

* Update setup.py to build cython extension package.
* Revisit build_readme.py in light of newly added support for markdown.
* Make sure that either pylama gets a bug fix or it's removed as a testing dependency.
  I had to hack it to get the code quality tests to work. I've submitted a 
  [bug report](https://github.com/klen/pylama/issues/160). Until this is taken care of, 
  the code can't ship as is.
* Regarding the `pyramids.trees module`: To clean up the code, separate data from 
  algorithms and separate tree structure from node data payload.

# Back Burner

When there's time to get around to it:

* Handle emergency parsing by ignoring properties when the best parse's score is sufficiently 
  terrible or no full-coverage tree is found.

* Add a precedence system to the grammar, allowing us to indicate just how desperate the 
  parser has to be before it even tries a particular rule. Then we can implement the above 
  to-do by having property-free versions automatically generated for each rule, with 
  last-ditch priority. It should also significantly reduce parsing time for certain situations 
  if we make less common usage have slightly lower precedence, by avoiding checking those 
  rules if they aren't worth it. Another option would be to have a score-based cutoff in the 
  parsing routine which disregards potential parse trees & stops early if a full- coverage 
  parse has been found and that parse's score is way higher than all the partial trees left to
  be considered. Or it could compare the score of each new parse tree to be considered against 
  its direct competitors instead of the parse as a whole, so we save time even when a parse 
  fails.

* Write a parser for a file that defines property inheritance; essentially, if a category of a 
  given name has a given property (or combination thereof) it also has such-and-such other
  properties. Then remove all rules that just do this from the grammar file and make them a 
  syntax error. The most important thing here is that we eliminate the 1000s of different 
  ways a single node can token_end_index up with the same properties just from adding them in a different 
  order. These property inheritance rules should be applied to every node before it is added 
  to the category map. To ensure conflicts don't cause issues due to variation in the order 
  the inheritance rules are applied, strict rules will have to be enforced on the order the 
  rules are applied. The simplest, most obvious answer is to apply them in the order they 
  appear in the file. It may be more appropriate to sort them according to some rule, however. 
  It may also be appropriate to restrict them, as well. For example, only allowing reference to 
  a negative property in the conditions if it is a property that cannot be added as a result. 
  (The *_ending properties are a good example; they can be supplied only by a leaf rule or 
  promotion. They will never be added by a property inheritance rule because they are really 
  properties of the token, not logical properties.) Now that I think about it, the only time a 
  negative property should be accessible as a condition in property inheritance is if it can 
  only apply to leaves. Properties should be divided into those that belong to leaves, and 
  those that also belong to branches. Leaf-only properties can be referenced as negatives in 
  the property inheritance, but branch properties cannot.

  I've rethought it again: negative properties can be conditions, but not effects. Positive 
  and negative properties are not resolved via cancellation until all inheritance rules have 
  finished firing; this lets every rule get a chance to fire without the issue of things 
  disappearing before it can due to other rules' actions. When all have fired and nothing new 
  can be added, positive properties overrule negative ones.

* When the user runs a training or test session, provide the option to automatically update 
  benchmarks if they match but not exactly.

* Record failures on both training & benchmarking sessions, and allow a training or 
  benchmarking session only for the most recently failed benchmark samples by commands of 
  the form "benchmark failures" and "train failures". Also, add a "failures" command which 
  lists failures in the form they are listed in for these two functions, and have these two 
  functions call into that command instead of printing them directly.

* Regarding parse tree node sets:
 
  Each of these really represents a group of parses having the same root form. In Parse, 
  when we get a list of ranked parses, we're ignoring all the other parses that have the 
  same root form. While this *usually* means we see all the parses we actually care to 
  see, sometimes there is an alternate parse with the same root form which actually has a 
  higher rank than the best representatives of other forms. When this happens, we want to 
  see this alternate form, but we don't get to. Create a method in Parse (along with 
  helper methods here) to allow the caller to essentially treat the Parse as a priority 
  queue for the best parses, so that we can iterate over *all* complete parses in order 
  of score and not just those that are the best for each root form, but without forcing 
  the caller to wait for every single complete parse to be calculated up front. That is,
  we should iteratively expand the parse set just enough to find the next best parse and 
  yield it immediately, keeping track of where we are in case the client isn't satisfied.

  Now that I think about it, the best way to implement this is literally with a priority 
  queue. We create an iterator for each top-level parse set, which iterates over each 
  alternative parse with the same root form, and we get the first parse from each one. We 
  then rank each iterator by the quality of the parse we got from it. We take the best 
  one & yield its parse, then grab another parse from it and re-rank the iterator by the 
  new parse, putting it back into the priority queue. If no more parses are available 
  from one of the iterators, we don't add it back to the priority queue. When the 
  priority queue is empty, we return from the method. Probably what's going to happen is 
  each of these iterators is actually going to use a recursive call back into the same 
  method for each child of the root node, putting the pieces together to create the next 
  best alternate parse.

* While functional, `GrammarParser.parse_conjunction_rule` is a copy/paste from 
  `parse_branch_rule`. Modify it to fit conjunctions more cleanly, or combine the two 
  methods.
