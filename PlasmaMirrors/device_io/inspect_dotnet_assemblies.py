"""
Inspect .NET assemblies (DLLs) using pythonnet and reflection.

Run locally in the same conda env that contains pythonnet. The script
loads each provided assembly path, then prints namespaces, types and
method signatures. Save output to a file and paste here if you want me to
help interpret which methods to call.

Usage:
  python device_io/inspect_dotnet_assemblies.py /path/to/DeviceIOLib.dll /path/to/CmdLib8742.dll --out report.txt

If pythonnet is not installed, the script prints instructions.
"""
from __future__ import annotations

import sys
import os
import argparse

def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(description='Inspect .NET assemblies using pythonnet')
    p.add_argument('assemblies', nargs='+', help='Paths to .NET DLLs (full path recommended)')
    p.add_argument('--out', '-o', help='Write output to file (otherwise prints to stdout)')
    args = p.parse_args(argv)

    try:
        import clr
        from System import AppDomain
        from System.Reflection import BindingFlags
    except Exception as e:
        print('pythonnet (clr) is required to run this script. Install it in your env:')
        print('  conda install -c conda-forge pythonnet')
        print('or')
        print('  python -m pip install pythonnet')
        print('\nFull exception:')
        print(e)
        return 2

    out_lines = []

    for asm_path in args.assemblies:
        asm_path = os.path.abspath(asm_path)
        if not os.path.exists(asm_path):
            out_lines.append(f'ERROR: assembly not found: {asm_path}\n')
            continue
        out_lines.append(f'== Assembly: {asm_path} ==')
        try:
            # Load from file path
            clr.AddReference(asm_path)
            # Get assembly by name
            # AppDomain.CurrentDomain.GetAssemblies may include it
            assemblies = AppDomain.CurrentDomain.GetAssemblies()
            asm = None
            for a in assemblies:
                try:
                    if os.path.abspath(a.Location).lower() == asm_path.lower():
                        asm = a
                        break
                except Exception:
                    # some dynamic assemblies may not have Location
                    continue
            if asm is None:
                # fallback: try load by name
                name = os.path.splitext(os.path.basename(asm_path))[0]
                try:
                    asm = __import__(name)
                except Exception:
                    asm = None

            if asm is None:
                out_lines.append('  WARNING: loaded via clr.AddReference, but assembly object not found via AppDomain lookup')
                out_lines.append('  Proceeding to try reflection through System.Reflection.Assembly.LoadFrom')
                from System.Reflection import Assembly
                asm = Assembly.LoadFrom(asm_path)

            # Use reflection to inspect types
            types = asm.GetTypes()
            for t in types:
                try:
                    tname = t.FullName
                except Exception:
                    tname = str(t)
                out_lines.append(f'-- Type: {tname}')
                # fields/properties
                try:
                    props = t.GetProperties()
                    if props.Length:
                        out_lines.append('   Properties:')
                        for pinfo in props:
                            out_lines.append(f'     {pinfo.PropertyType.Name} {pinfo.Name}')
                except Exception:
                    pass
                try:
                    fields = t.GetFields()
                    if fields.Length:
                        out_lines.append('   Fields:')
                        for finfo in fields:
                            out_lines.append(f'     {finfo.FieldType.Name} {finfo.Name}')
                except Exception:
                    pass
                # methods
                try:
                    methods = t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                    if methods.Length:
                        out_lines.append('   Methods:')
                        for m in methods:
                            try:
                                sig = m.ToString()
                            except Exception:
                                sig = m.Name
                            out_lines.append(f'     {sig}')
                except Exception:
                    pass
        except Exception as e:
            out_lines.append(f'  ERROR inspecting assembly: {e}')

        out_lines.append('')

    text = '\n'.join(out_lines)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'Wrote reflection report to {args.out}')
    else:
        print(text)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
