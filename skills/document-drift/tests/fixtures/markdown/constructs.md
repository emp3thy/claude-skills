Front matter style title
========================

<!-- document-drift: ignore-next -->
<!--
  multi-line comment with `not code`
-->

## ATX heading with `inline/code.py` ##

Sub heading
-----------

A paragraph with `src/app.py`, a span that continues `across
a line break`, a multi-backtick span `` a`b `` and an escaped \`tick\`.
Unmatched ``` backticks stay literal and `` this ` too.

Links: [the guide](docs/guide.md "Guide"), [`code label`](src/x.py),
[angle](<docs/with space.md>), [escaped](docs/a\_b.md), [entity](docs/a&amp;b.md),
[nested (parens)](docs/a_(b).md) and [empty]().

Images: ![logo](assets/logo.png) and a badge [![ci](https://ci.example/badge.svg)](https://ci.example).

Autolinks: <https://example.com/x> and <mailto:a@b.co> and <ops@example.com>.

Reference links: [full][guide], [Guide][], [GUIDE], [two][two-line] and ![img ref][logo-ref].
Undefined [nothing][missing] stays text. Inline <span title="`x`">raw html</span> and <!-- inline comment -->.

[guide]: docs/guide.md "The guide"
[logo-ref]: <assets/logo ref.png>
[two-line]:
  docs/two-line.md

```bash
make build
echo `not inline`
```

~~~
```
tilde fence holding a backtick fence line
```
~~~

````markdown
```python
inner
```
````

```
unclosed-looking ~~~ line
~~~
`````

- item one with `scripts/run.sh`
- item two

  ```sh
  ./scripts/indented.sh
  ```

  Second paragraph of item two with `docs/x.md`.
  - nested `a/b.py`
    - deeper `c/d.py`
1. ordered `one.txt`
2. ordered `two.txt`
lazy continuation `lazy.txt`

*	Tab after marker `tab.txt`
	continued under the tab

| Column | Value |
|:-------|------:|
| `a\|b` | `c` |
| [link](docs/t.md) | plain |
| `x` |

> Quoted `quote.py` text
> with [a link](docs/q.md)
lazy quote line `lazy-quote.py`

    indented code `not/inline.py`
    more

<details>
<summary>Raw `html` block</summary>

Inside details `details.md`.

</details>

***

Trailing paragraph `end.md`.
