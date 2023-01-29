import requests
import re

SOURCE_BASE_URL = "https://raw.githubusercontent.com/blender/blender/"

def gen_import():
    body = '''from ctypes import (
    c_void_p, c_char, c_short, c_int, c_int8,
    addressof, cast, pointer,
    Structure,
    POINTER,
)
    '''

    print(body)


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


def type_to_ctype(type, is_pointer):
    known_struct = (
        "Link",
        "ListBase",
        "ScrAreaMap",
        "wmWindow",
        "wmOperator",
        "wmEventHandler",
        "eWM_EventHandlerType",
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
    if type in builtin_types:
        if is_pointer:
            return True, f"c_{type}_p"
        return True, f"c_{type}"

    assert is_pointer
    return False, "c_void_p"


def gen_struct(tag, source_file_path, struct_name, add_method_func):
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

    print(f"class {struct_name}(Structure):")
    print(f'    """Defined in ${source_file_path}"""')
    if callable(add_method_func):
        print(add_method_func())
    print("\n")
    print("# pylint: disable=W0212")
    print(f"{struct_name}._field_ = [")
    for var in variables:
        known_type, type_name = type_to_ctype(var["type"], var["is_pointer"])
        if var["array_element_num"]:
            type_name = f'{type_name} * {var["array_element_num"]}'
        if known_type:
            print(f'    ("{var["name"]}", {type_name}),')
        else:
            print(f'    ("{var["name"]}", {type_name}),   # {var["type"]}')
    print("]")
    print("\n")


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
            newlink.next.prev = gen_ptr(newlink)
    '''

    return body


def main():
    tag = "v3.0.0"
    gen_info = [
        ["source/blender/makesdna/DNA_listBase.h", "Link", None],
        ["source/blender/makesdna/DNA_listBase.h", "ListBase", add_method_for_ListBase],
        ["source/blender/makesdna/DNA_screen_types.h", "ScrAreaMap", None],
        ["source/blender/makesdna/DNA_windowmanager_types.h", "wmWindow", None],
        ["source/blender/makesdna/DNA_windowmanager_types.h", "wmOperator", None],
        ["source/blender/windowmanager/wm_event_system.h", "wmEventHandler", None],
    ]

    gen_import()
    for info in gen_info:
        gen_struct(tag, info[0], info[1], info[2])


main()