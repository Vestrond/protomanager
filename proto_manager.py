import re
from collections import OrderedDict


STRING_TYPES = [
    'string',
    'google.protobuf.StringValue',
]

INT_TYPES = [
    'int32', 'int64',
    'uint32', 'uint64',
    'sint32', 'sint64',
    'fixed32', 'fixed64',
    'sfixed32', 'sfixed64',
    'google.protobuf.Int32Value', 'google.protobuf.Int64Value',
]

FLOAT_TYPES = [
    'float', 'double',
]

BOOL_TYPES = [
    'bool',
    'google.protobuf.BoolValue',
]

BYTES_TYPES = [
    'bytes',
]


def is_base_type(field_type):
    # type: (str) -> bool
    return field_type in STRING_TYPES + FLOAT_TYPES + INT_TYPES + BOOL_TYPES + BYTES_TYPES


class MessageField:
    def __init__(self, field_type=None, is_repeated=False, is_required=False, value=None):
        # type: (str, bool, bool, ...) -> None
        self.type = field_type  # type: str
        self.is_repeated = is_repeated  # type: bool
        self.is_required = is_required  # type: bool
        self.is_base_type = is_base_type(field_type)  # type: bool
        self.is_map = field_type.startswith('map<')  # type: bool
        self.value = value

    def __str__(self):
        return "MessageField(type='%s', isRepeated=%r, isRequired=%r, isEmpty=%r)" % \
               (self.type, self.is_repeated, self.is_required, self.value is None)

    def __repr__(self):
        return self.__str__()


class EnumField:
    def __init__(self, name):
        # type: (str) -> None
        self.name = name
        self.values = []


class ProtoFile:
    FIELDS_KEY = '__fields__'

    def __init__(self, filename):
        self.__go_package = None
        self.__package = None
        self.__imported_packages = dict()

        self.__structure = OrderedDict()

        # oneof
        self.__is_oneof_block = False

        # enum
        self.__is_enum_block = False
        self.__enum_name = None

        # message
        self.__message_block = None
        # path to block, like: ["Button", "theme", "text", "font"]
        self.__message_names_path = []

        self.__parse_file(filename)

    @property
    def go_package(self):
        return self.__go_package

    @property
    def package(self):
        return self.__package

    @property
    def imports(self):
        return self.__imported_packages

    @property
    def structure(self):
        return self.__structure

    @property
    def fields_key(self):
        return self.FIELDS_KEY

    # Merge several files with one package
    def merge_proto_file(self, proto_file):
        # type: (ProtoFile) -> None
        self.__structure.update(proto_file.structure)
        self.__imported_packages.update(proto_file.imports)

    def __parse_file(self, filename):
        with open(filename, 'r') as read:
            for line in read:
                self.__parse_line(line)

    def __parse_line(self, line):
        line = line.strip()

        if line.startswith('option go_package '):
            package = re.match(r"option go_package = \"(?P<package>.+)\";", line).groupdict()['package']
            self.__go_package = package

        elif line.startswith('package'):
            package = re.match(r"package (?P<name>\w+);", line).groupdict()['name']
            self.__package = package

        elif line.startswith('import '):
            field = re.match(r"import \"(?P<field>.+.proto)\";", line).groupdict()['field']
            self.__add_import_field(field)

        elif line.startswith('message '):
            message_name = re.match(r"message (?P<name>\w+) {", line).groupdict()['name']
            self.__add_message(message_name)

        elif line.startswith('enum '):
            enum_name = re.match(r"enum (?P<name>\w+) {", line).groupdict()['name']
            self.__add_enum(enum_name)

        elif line.startswith('oneof '):
            self.__is_oneof_block = True

        elif line.startswith('}'):
            self.__close_block()

        elif line.startswith('//'):
            pass

        elif line == '':
            pass

        else:
            # Probably this line is enum's field...
            if self.__is_enum_block:
                if line.startswith('reserved'):
                    # Honestly, now I have no idea what to do with reserved fields
                    return

                value = re.match(r"(?P<key>\w+) = \d+;", line).groupdict()['key']
                self.__set_enum_value(value)
                return

            # ...or message's field
            if self.__message_block is not None:
                info_dict = re.match(
                    r"(repeated )?(?P<field_type>.+) (?P<name>\w+) = (?P<index>\d+);(// required)?",
                    line,
                ).groupdict()
                is_repeated = line.startswith('repeated ')
                is_required = line.endswith('// required')

                new_field = MessageField(info_dict['field_type'], is_repeated, is_required)

                self.__add_field(info_dict['name'], new_field)

    def __add_import_field(self, field):
        # type: (str) -> None
        if not field.startswith('proto'):
            return

        proto_module = ProtoFile(field)
        if proto_module.package not in self.__imported_packages:
            self.__imported_packages[proto_module.package] = proto_module
        else:
            self.__imported_packages[proto_module.package].merge_proto_file(proto_module)

    def __get_current_message_block(self):
        # type: () -> (dict | None)
        if self.__message_block is None:
            return

        target = self.__message_block
        # go deep through structure to current block
        for name in self.__message_names_path:
            target = target[name]

        return target

    def __add_message(self, name):
        # type: (str) -> None
        if self.__message_block is None:
            self.__message_block = {
                name: {self.FIELDS_KEY: OrderedDict()},
            }
            self.__message_names_path.append(name)
        else:
            target = self.__get_current_message_block()
            target[name] = {self.FIELDS_KEY: OrderedDict()}
            # WARN: should be after `__get_current_message_block`, not before
            self.__message_names_path.append(name)

    def __add_enum(self, name):
        # type: (str) -> None
        self.__is_enum_block = True
        self.__enum_name = name

        block = self.__get_current_message_block()
        if block is None:
            self.__structure[name] = EnumField(name)
        else:
            block[name] = EnumField(name)

    def __set_enum_value(self, value):
        # type: (object | str | int) -> None
        block = self.__get_current_message_block()
        if block is None:
            field = self.__structure[self.__enum_name]
        else:
            field = block[self.__enum_name]

        field.values.append(value)

    def __close_block(self):
        if self.__is_enum_block:
            self.__is_enum_block = False
            self.__enum_name = None

        elif self.__is_oneof_block:
            self.__is_oneof_block = False

        elif len(self.__message_names_path) > 1:
            self.__message_names_path.pop()

        else:
            self.__structure[self.__message_names_path[0]] = self.__message_block[self.__message_names_path[0]]
            self.__message_block = None
            self.__message_names_path = []

    def __add_field(self, name, field):
        # type: (str, MessageField) -> None
        if self.__message_block is None:
            return

        block = self.__get_current_message_block()
        block[self.FIELDS_KEY][name] = field

    def has_in_imports(self, field_type):
        # type: (str) -> bool
        # Example: Check that 'core.Icon' in imported packages.
        if '.' not in field_type:
            return False

        # 'interface.Button' -> ['interface', 'Button']
        pkg, msg = field_type.split('.', 1)
        if pkg in self.__imported_packages and msg in self.__imported_packages[pkg].structure:
            return True

        return False

    def get_import_package(self, field_type):
        # type: (str) -> ProtoFile
        # 'interface.Button' -> ['interface', 'Button']
        package, unused_message = field_type.split('.', 1)
        return self.__imported_packages[package]

    def get_import_package_as_structure(self, field_type):
        # type: (str) -> OrderedDict
        # 'interface.Button' -> ['interface', 'Button']
        package, message = field_type.split('.', 1)
        pkg = self.__imported_packages[package]  # type: ProtoFile
        return pkg.structure[message]
