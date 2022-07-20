#!/usr/bin/env python3
# Reimplementation of makerel by RootCubed

import os
from pathlib import Path
from elftools.elf.elffile import ELFFile
from relfile import REL, RelocType, Relocation, Section

def print_warn(msg: str):
    print(f'\033[33m{msg}\033[39m')

def print_err(msg: str):
    print(f'\033[31m{msg}\033[39m')

def print_success(msg: str):
    print(f'\033[32m{msg}\033[39m')

str_file = ""
id = 1
unresolved_symbol_count = 0

def process_file(modules: list[ELFFile], idx: int, filename: Path):
    global id, str_file, unresolved_symbol_count
    
    # Generate .str file and output filename
    str_file_offset = len(str_file)
    path_str = f'{os.path.abspath(filename)}\0'
    str_file += path_str

    outfile = filename.with_suffix('.rel')

    # Create REL
    rel_file = REL(id, path_offset=str_file_offset, path_size=len(path_str))
    id += 1

    elffile = modules[idx]
    module_relocations: dict[int, list[Relocation]] = {}

    for section in elffile.iter_sections():
        if section['sh_type'] != 'SHT_PROGBITS' or section.name == '.comment':
            # Non-text/data sections are added to the REL as empty sections
            rel_file.add_section(Section())
            continue

        rel_sec = Section()
        rel_sec.set_data(bytearray(section.data()))
        rel_sec.executable = section.name == '.text'
        rel_sec.alignment = section['sh_addralign']
        rel_file.add_section(rel_sec)

        rela_sec = elffile.get_section_by_name('.rela' + section.name)
        if not rela_sec:
            continue

        symbol_table = elffile.get_section(rela_sec['sh_link'])

        module_classify: dict[int, list] = {}
        relocs_sorted = []

        for reloc in rela_sec.iter_relocations():
            relocs_sorted.append(reloc)

        relocs_sorted.sort(key=lambda r: r['r_offset'])
        for reloc in relocs_sorted:
            symbol = symbol_table.get_symbol(reloc['r_info_sym'])

            # Find module which contains the symbol
            found_sym = False
            for (i, mod) in enumerate(modules):
                symtab = mod.get_section_by_name('.symtab')
                try_found = symtab.get_symbol_by_name(symbol.name)
                if try_found and try_found[0]['st_shndx'] != 'SHN_UNDEF':
                    if i not in module_classify:
                        module_classify[i] = [(reloc, try_found[0])]
                    else:
                        module_classify[i].append((reloc, try_found[0]))
                    found_sym = True
                    break
            if not found_sym:
                print_err(f'Error: Symbol {symbol.name} not found!')
                unresolved_symbol_count += 1

        for mod in module_classify:
            if mod not in module_relocations:
                module_relocations[mod] = []

            change_section_reloc = Relocation()
            change_section_reloc.reloc_type = RelocType.R_RVL_SECT
            change_section_reloc.offset = 0
            change_section_reloc.section = idx + 1
            change_section_reloc.addend = 0
            module_relocations[mod].append(change_section_reloc)
            pos = 0

            for (rel, sym) in module_classify[mod]:
                assert rel['r_offset'] >= pos
                out_reloc = Relocation()
                out_reloc.offset = rel['r_offset'] - pos
                pos = rel['r_offset']
                out_reloc.reloc_type = RelocType(rel['r_info_type'])
                out_reloc.section = sym['st_shndx']
                out_reloc.addend = sym['st_value']
                module_relocations[mod].append(out_reloc)

    # Append final relocation
    for mod in module_relocations:
        stop_reloc = Relocation()
        stop_reloc.reloc_type = RelocType.R_RVL_STOP
        stop_reloc.offset = 0
        stop_reloc.section = 0
        stop_reloc.addend = 0
        module_relocations[mod].append(stop_reloc)
        rel_file.relocations[mod] = module_relocations[mod]

    # Create BSS section
    section = elffile.get_section_by_name('.bss')
    if section:
        rel_file.bss_size = section.data_size
        bss_sec = Section()
        bss_sec.is_bss = True
        bss_sec._sec_len = section.data_size
        rel_file.add_section(bss_sec)

    # Generate prolog, epilog and unresolved
    symtab = elffile.get_section_by_name('.symtab')
    prolog = symtab.get_symbol_by_name('_prolog')
    if prolog:
        rel_file.prolog_section = prolog[0]['st_shndx']
        rel_file.prolog = prolog[0]['st_value']

    epilog = symtab.get_symbol_by_name('_epilog')
    if epilog:
        rel_file.epilog_section = epilog[0]['st_shndx']
        rel_file.epilog = epilog[0]['st_value']

    unresolved = symtab.get_symbol_by_name('_unresolved')
    if unresolved:
        rel_file.unresolved_section = unresolved[0]['st_shndx']
        rel_file.unresolved = unresolved[0]['st_value']

    # Write file
    with open(outfile, 'wb') as f:
        rel_file.write(f)


if __name__ == '__main__':

    # Parse arguments separately so this file can be imported from other ones
    import argparse
    parser = argparse.ArgumentParser(description='Compiles REL files')
    parser.add_argument('elf_file', type=Path)
    parser.add_argument('plf_files', type=Path, nargs='+')
    args = parser.parse_args()

    # Call actual function
    if args.elf_file.is_file():
        if not any([not plf.is_file() for plf in args.plf_files]):

            # Open files and parse them
            files = [open(args.elf_file, 'rb')] + [open(plf, 'rb') for plf in args.plf_files]
            modules = [ELFFile(f) for f in files]

            # Process them
            for idx in range(1, len(modules)):
                process_file(modules, idx, args.plf_files[idx-1])
                if unresolved_symbol_count > 0:
                    print_warn(f'Processed {args.plf_files[idx-1]} with {unresolved_symbol_count} unresolved symbol(s).')
                else:
                    print_success(f'Processed {args.plf_files[idx-1]}.')

            # Close them
            for file in files:
                file.close()
        else:
            print_err('Some PLF files are missing!')
        
        with open(args.elf_file.with_suffix('.str'), 'w') as f:
            f.write(str_file)
        print_success(f'Wrote {f.name}.')
    else:
        print_err('File', args.elf_file, 'not found!')
    