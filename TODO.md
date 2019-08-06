
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
  ways a single node can end up with the same properties just from adding them in a different 
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

* next