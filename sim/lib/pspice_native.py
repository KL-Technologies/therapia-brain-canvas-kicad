#!/usr/bin/env python3
"""TI's PSpice models rewritten into ngspice's own syntax, so no deck needs
ngspice's PSpice compatibility mode.

    python3 sim/lib/pspice_native.py        (re)write sim/models/vendor/native/

Why
---
`set ngbehavior=psa` made TI's models parse, but in PSpice mode ngspice
45.2 (the one KiCad 10.0.5 bundles) prepends its own helper functions to
every deck -- `.func pwr(x, a) { pow(x, a) }`, `pwrs`, `stp`, `if` -- and
now and then fails to parse the first of them ("failed to parse .func in:
.func pwr(x a) { pow(x,a)}"), which leaves the library unusable. It was
measured at 1 in 3 with the XSPICE code models loaded and 6 in 6 without,
with or without a spinit file; retrying only hid it. The helpers exist for
PSpice syntax. A deck with none has no reason to be in that mode, and then
ngspice never injects them.

What is rewritten
-----------------
The TI files stay verbatim in sim/models/vendor/ and are the source; this
writes sim/models/vendor/native/<same name> with these textual changes, and
nothing else:

  IF( / IF (            -> ternary_fcn(     (ngspice's own name for PSpice IF)
  &  |  inside {...}    -> &&  ||
  {{ ... }}             -> { ... }          (PSpice's doubled braces)
  {PARAM} inside an expression -> PARAM     (a brace inside a brace)
  VALUE { / VALUE = {   -> VALUE={          (ngspice's spelling)
  .MODEL x VSWITCH Roff= Ron= Voff= Von=
                        -> .model ax pswitch(cntl_on= cntl_off= r_on= r_off= log=TRUE)
  S n+ n- nc+ nc- x     -> aS %gd(nc+ nc-) %gd(n+ n-) ax
                           (exactly ngspice's own PSpice-mode translation, read
                           from its templates; pswitch is in xtradev.cm)
  R ... TC=0,0          -> R ...            (both coefficients are zero)
  .IC V(n) {x}          -> .IC V(n)={x}
  .include x_pspice.lib -> .include x_pspice.lib (the native copy beside it)

`sim/cases/power_tree_startup.py` runs both TI models from the native copies
and asks the same questions as before; the equivalence against the PSpice
mode run is recorded in sim/models/PROVENANCE.md.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(os.path.dirname(HERE), "models", "vendor")
NATIVE = os.path.join(VENDOR, "native")
FILES = ["lm2664_ti_pspice.lib", "lm2664_ti.lib",
         "tps72301_ti_pspice.lib", "tps72325_ti.lib"]


def join_continuations(lines):
    out = []
    for line in lines:
        if line.startswith("+") and out and not out[-1].startswith("*"):
            out[-1] = out[-1].rstrip("\n") + " " + line[1:]
        else:
            out.append(line)
    return out


def fix_expr(body):
    """The inside of one {...} expression."""
    body = re.sub(r"\bIF\s*\(", "ternary_fcn(", body, flags=re.I)
    body = re.sub(r"(?<![&|])&(?![&])", "&&", body)
    body = re.sub(r"(?<![&|])\|(?![|])", "||", body)
    body = body.replace("{", "").replace("}", "")
    return body


def fix_braces(line):
    """Rewrite every outermost {...} of a line through fix_expr."""
    out, i = [], 0
    while i < len(line):
        if line[i] == "{":
            depth, j = 0, i
            while j < len(line):
                if line[j] == "{":
                    depth += 1
                elif line[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append("{" + fix_expr(line[i + 1:j]) + "}")
            i = j + 1
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


def fix_vswitch(line):
    """PSpice's VSWITCH, the way ngspice's own PSpice mode translates it (the
    templates in libngspice 45.2: ".model a%s pswitch(... log=TRUE)" and
    "a%s %gd(%s %s) %gd(%s %s) a%s"): the XSPICE pswitch from xtradev.cm,
    which the driver loads."""
    m = re.match(r"(\s*)\.MODEL\s+(\S+)\s+VSWITCH\s*(.*)$", line, re.I)
    if not m:
        return line
    kv = dict((k.lower(), v) for k, v in
              re.findall(r"(\w+)\s*=\s*([^\s)]+)", m.group(3)))
    return ("%s.model a%s pswitch(cntl_on=%s cntl_off=%s r_on=%s r_off=%s "
            "log=TRUE)\n" % (m.group(1), m.group(2), kv["von"], kv["voff"],
                              kv["ron"], kv["roff"]))


def fix_switch_instance(line, models):
    """S<n> n+ n- nc+ nc- <model>  ->  a<n> %gd(nc+ nc-) %gd(n+ n-) a<model>"""
    m = re.match(r"(\s*)(S\S*)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$",
                 line, re.I)
    if not m or m.group(7).lower() not in models:
        return line
    return ("%sa%s %%gd(%s %s) %%gd(%s %s) a%s\n"
            % (m.group(1), m.group(2), m.group(5), m.group(6), m.group(3),
               m.group(4), m.group(7)))


def convert(text):
    lines = join_continuations(text.splitlines(True))
    models = {m.group(1).lower() for m in
              (re.match(r"\s*\.MODEL\s+(\S+)\s+VSWITCH", l, re.I)
               for l in lines) if m}
    out = []
    for line in lines:
        if line.lstrip().startswith("*"):
            out.append(line)
            continue
        line = re.sub(r"\bVALUE\s*=?\s*\{", "VALUE={", line, flags=re.I)
        line = re.sub(r"\s+TC\s*=\s*0\s*,\s*0\b", "", line, flags=re.I)
        line = re.sub(r"^(\s*\.IC\s+V\([^)]*\))\s*\{", r"\1={", line, flags=re.I)
        line = fix_vswitch(line)
        line = fix_switch_instance(line, models)
        line = fix_braces(line)
        out.append(line)
    return "".join(out)


def main():
    if not os.path.isdir(NATIVE):
        os.makedirs(NATIVE)
    for name in FILES:
        with open(os.path.join(VENDOR, name)) as fh:
            src = fh.read()
        head = ("* GENERATED by sim/lib/pspice_native.py from ../%s -- do not "
                "edit.\n* ngspice-native syntax; the TI original is untouched "
                "beside it.\n" % name)
        with open(os.path.join(NATIVE, name), "w") as fh:
            fh.write(head + convert(src))
        print("wrote", os.path.join("sim/models/vendor/native", name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
