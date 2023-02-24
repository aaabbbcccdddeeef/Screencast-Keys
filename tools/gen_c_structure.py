import argparse
import requests
import re
import sys

SOURCE_BASE_URL = "https://raw.githubusercontent.com/blender/blender/"

def gen_import(file):
    body = '''from ctypes import (
    c_void_p, c_char, c_short, c_int, c_int8,
    addressof, cast, pointer,
    Structure,
    POINTER,
)
    '''

    print(f"{body}\n", file=file)


def parse_struct(code_body, struct_name):
    lines = code_body.split("\n")
    variables = []
    for l in lines:
        m = re.search(r"^\s*(enum\s+|struct\s+)*([a-zA-Z_][a-zA-Z0-9_]*)\s+([a-zA-Z0-9_\[\],\s*]*?)(\s+DNA_DEPRECATED)*;", l)
        if m:
            var_names = m.group(3).split(",")
            for name in var_names:
                name = name.strip()

                var = {}
                var["is_pointer"] = name.startswith("*")
                var["type"] = m.group(2)

                name = name[1:] if var["is_pointer"] else name
                m2 = re.search(r"^([a-zA-Z0-9_]+)(\[([0-9]+)\])*$", name)
                if not m2:
                    raise Exception(f"Unexpected line: {l}")
                var["name"] = m2.group(1)
                var["array_element_num"] = int(m2.group(3)) if m2.group(2) else None
                variables.append(var)

    return variables


def parse_enum(code_body, enum_name):
    lines = code_body.split("\n")
    items = []
    value = 0
    for l in lines:
        m = re.search(r"^\s*([A-Z_]+)\s*(=*)\s*([0-9]*),", l)
        if m:
            item = {}
            item["name"] = m.group(1)
            if m.group(2) == "=":
                item["value"] = int(m.group(3))
                value = item["value"] + 1
            else:
                item["value"] = value
                value += 1
            items.append(item)

    return items


def type_to_ctype(type, is_pointer):
    known_struct = (
        "Link",
        "ListBase",
        "ScrAreaMap",
        "wmWindow",
        "wmOperator",
        "wmEventHandler",
    )
    known_enum = (
        "eWM_EventHandlerType",
        "eWM_EventHandlerFlag",
    )
    known_func = (
        "EventHandlerPoll",
    )
    builtin_types = (
        "void",
        "char",
        "short",
        "int",
        "int8",
    )

    if type in known_struct:
        if is_pointer:
            return True, f"POINTER({type})"
        return True, type
    if type in known_enum:
        return False, f"c_int8"
    if type in known_func:
        return False, f"c_void_p"
    if type in builtin_types:
        if is_pointer:
            return True, f"c_{type}_p"
        return True, f"c_{type}"

    assert is_pointer
    return False, "c_void_p"


def gen_struct(file, tag, source_file_path, struct_name, add_method_func, add_variable_func):
    url = f"{SOURCE_BASE_URL}/{tag}/{source_file_path}"
    response = requests.get(url)
    response.raise_for_status()
    
    code_body = response.text
    lines = code_body.split("\n")
    in_struct = False
    struct_code_body = ""
    for l in lines:
        if not in_struct:
            m = re.search(r"struct\s+" + struct_name + r"\s+{$", l)
            if m:
                in_struct = True
        else:
            struct_code_body += l + "\n"
            m = re.search("^}", l)
            if m:
                break
    else:
        raise Exception(f"Struct {struct_name} is not found.")

    variables = parse_struct(struct_code_body, struct_name)

    def print_variable(file, var):
        known_type, type_name = type_to_ctype(var["type"], var["is_pointer"])
        if var["array_element_num"]:
            type_name = f'{type_name} * {var["array_element_num"]}'
        if known_type:
            print(f'    ("{var["name"]}", {type_name}),', file=file)
        else:
            print(f'    ("{var["name"]}", {type_name}),   # {var["type"]}', file=file)

    print(f"class {struct_name}(Structure):", file=file)
    print(f'    """Defined in ${source_file_path}"""', file=file)
    if callable(add_method_func):
        print(add_method_func(), file=file)
    print("\n", file=file)
    print("# pylint: disable=W0212", file=file)
    print(f"{struct_name}._fields_ = [", file=file)
    for var in variables:
        print_variable(file, var)
    if callable(add_variable_func):
        variables_to_add = add_variable_func()
        for var in variables_to_add:
            print_variable(file, var)
    print("]", file=file)
    print("\n", file=file)


def gen_enum(file, tag, source_file_path, enum_name):
    url = f"{SOURCE_BASE_URL}/{tag}/{source_file_path}"
    response = requests.get(url)
    response.raise_for_status()
    
    code_body = response.text
    lines = code_body.split("\n")
    in_enum = False
    enum_code_body = ""
    for l in lines:
        if not in_enum:
            m = re.search(r"enum\s+" + enum_name + r"\s+{$", l)
            if m:
                in_enum = True
        else:
            enum_code_body += l + "\n"
            m = re.search("^}", l)
            if m:
                break
    else:
        raise Exception(f"Enumerator {enum_name} is not found.")

    items = parse_enum(enum_code_body, enum_name)

    print("# pylint: disable=C0103", file=file)
    print(f"class {enum_name}:", file=file)
    print(f'    """Defined in ${source_file_path}"""\n', file=file)
    for item in items:
        print(f'    {item["name"]} = {item["value"]}', file=file)
    print("\n", file=file)


def add_method_for_ListBase():
    body = '''
    def remove(self, vlink):
        """Ref: BLI_remlink"""

        link = vlink
        if not vlink:
            return

        if link.next:
            link.next.contents.prev = link.prev
        if link.prev:
            link.prev.contents.next = link.next

        if self.last == addressof(link):
            self.last = cast(link.prev, c_void_p)
        if self.first == addressof(link):
            self.first = cast(link.next, c_void_p)

    def find(self, number):
        """Ref: BLI_findlink"""

        link = None
        if number >= 0:
            link = cast(c_void_p(self.first), POINTER(Link))
            while link and number != 0:
                number -= 1
                link = link.contents.next
        return link.contents if link else None

    def insert_after(self, vprevlink, vnewlink):
        """Ref: BLI_insertlinkafter"""

        prevlink = vprevlink
        newlink = vnewlink

        if not newlink:
            return

        def gen_ptr(link):
            if isinstance(link, (int, type(None))):
                return cast(c_void_p(link), POINTER(Link))
            else:
                return pointer(link)

        if not self.first:
            self.first = self.last = addressof(newlink)
            return

        if not prevlink:
            newlink.prev = None
            newlink.next = gen_ptr(self.first)
            newlink.next.contents.prev = gen_ptr(newlink)
            self.first = addressof(newlink)
            return

        if self.last == addressof(prevlink):
            self.last = addressof(newlink)

        newlink.next = prevlink.next
        newlink.prev = gen_ptr(prevlink)
        prevlink.next = gen_ptr(newlink)
        if newlink.next:
            newlink.next.prev = gen_ptr(newlink)'''

    return body


def add_variable_for_wmEventHandler():
    variables = [
        {
            "name": "op",
            "type": "wmOperator",
            "is_pointer": True,
            "array_element_num": None,
        },
    ]

    return variables


def parse_argument():
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", nargs="?", type=argparse.FileType("w"), default=sys.stdout)
    parser.add_argument("-t", "--target", nargs="?", type=str, default="main")

    args = parser.parse_args()
    return args


def main():
    args = parse_argument()

    output_file = args.output
    target = args.target
    gen_info = [
        ["enum", "source/blender/windowmanager/wm_event_system.h", "eWM_EventHandlerType"],

        ["struct", "source/blender/makesdna/DNA_listBase.h", "Link", None, None],
        ["struct", "source/blender/makesdna/DNA_listBase.h", "ListBase", add_method_for_ListBase, None],
        ["struct", "source/blender/makesdna/DNA_screen_types.h", "ScrAreaMap", None, None],
        ["struct", "source/blender/makesdna/DNA_windowmanager_types.h", "wmWindow", None, None],
        ["struct", "source/blender/makesdna/DNA_windowmanager_types.h", "wmOperator", None, None],
        ["struct", "source/blender/windowmanager/wm_event_system.h", "wmEventHandler", None, add_variable_for_wmEventHandler],
    ]

    gen_import(output_file)
    for info in gen_info:
        if info[0] == "struct":
            gen_struct(output_file, target, info[1], info[2], info[3], info[4])
        elif info[0] == "enum":
            gen_enum(output_file, target, info[1], info[2])

if __name__ == "__main__":
    main()
