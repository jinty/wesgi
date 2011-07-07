CHANGES
=======

0.8 (unreleased)
----------------

Features
++++++++

- A ``max_object_size`` option for ``wesgi.LRUCache`` to limit the maximum size
  of objects stored.

0.7 (2011-07-06)
----------------

Features
++++++++

- Major refactoring to use ``httplib2`` as the backend to get ESI includes. This
  brings along HTTP Caching.
- A memory based implementation of the LRU caching algoritm at ``wesgi.LRUCache``.
- Handle ESI comments.

Bugfixes
++++++++

- Fix bug where regular expression to find ``src:includes`` could take a long time.

0.5 (2011-07-04)
----------------

- Initial release.
