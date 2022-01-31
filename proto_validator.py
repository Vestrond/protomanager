import re
from collections import OrderedDict

from .proto_manager import ProtoFile, MessageField, EnumField, \
    STRING_TYPES, FLOAT_TYPES, INT_TYPES, BOOL_TYPES, \
    is_base_type


class ProtoValidator:
    def __init__(self):
        self.__errors = []

    def __add_errors(self, test_path, errors):
        # type: (str, str | [str] | None) -> None
        if errors is None:
            return

        # 'type(...).__name__' cus python 3.0+ have no 'unicode' type
        if type(errors).__name__ in ['str', 'unicode']:
            self.__errors.append("%s: %s" % (test_path, errors))

        if type(errors) == list:
            for error in errors:
                self.__add_errors(test_path, error)

    @staticmethod
    def __validate_base_type(proto_type, test_value):
        # type: (str, ...) -> str | None
        type_associations = [
            [STRING_TYPES, ['str', 'unicode']],
            [FLOAT_TYPES, ['float']],
            [INT_TYPES, ['int', 'long']],
            [BOOL_TYPES, ['bool']],
            # TODO: Find a way to check bytes type.
            # [BYTES_TYPES, ['bytearray']],
        ]

        for proto_types, python_types in type_associations:
            # 'type(...).__name__' cus python 3.0+ have no 'unicode' type
            if proto_type in proto_types and type(test_value).__name__ not in python_types:
                return "wrong type. Expected type [%s], got [%s] (as %r) instead." \
                       % (proto_type, type(test_value).__name__, test_value)

    def __validate_multiply_base_types(self, proto_type, test_value):
        # type: (str, ...) -> [str] | None
        errors = []

        for value in test_value:
            errors.append(self.__validate_base_type(proto_type, value))

        return errors

    def __validate_map_type(self, proto_file, proto_type, test_value, test_path):
        # type: (ProtoFile, str, ..., str) -> [str] | None
        if type(test_value) != dict:
            return [
                "not a valid map. Expected type [%s], got [%s] (as %r) instead."
                % (proto_type, type(test_value).__name__, test_value)
            ]

        errors = []

        for key, value in test_value.items():
            map_value_type = re.match(r"map<\w+, ?(?P<value>[\w.]+)>", proto_type).groupdict()['value']

            if is_base_type(map_value_type):
                error = self.__validate_base_type(map_value_type, value)
            else:
                new_proto_file = proto_file.get_import_package(map_value_type)
                new_proto_scope = proto_file.get_import_package_as_structure(map_value_type)
                self.__validate_structure(
                    new_proto_file, new_proto_scope, value, "%s > %s" % (test_path, key), map_value_type
                )
                error = None

            if error is not None:
                errors.append(
                    "wrong value's type for key '%s'. Expected type [%s] (from [%s]), got [%s] (as %r) instead."
                    % (key, map_value_type, proto_type, type(value).__name__, value)
                )

        return errors

    @staticmethod
    def __validate_enum_type(enum_field, test_value):
        # type: (EnumField, ...) -> str | None
        if test_value not in enum_field.values:
            return "unknown value '%s' for [enum %s]." % (test_value, enum_field.name)

    def __validate_multiply_enum_types(self, enum_field, test_value):
        # type: (EnumField, ...) -> [str] | None
        errors = []

        for value in test_value:
            errors.append(self.__validate_enum_type(enum_field, value))

        return errors

    @staticmethod
    def __validate_and_del_excess(proto_fields, test_data):
        # type: (OrderedDict, dict) -> [str]
        keys_to_del = []
        errors = []

        for test_key in test_data.keys():
            if test_key not in proto_fields.keys():
                errors.append("field '%s' is excess." % test_key)
                keys_to_del.append(test_key)

        for key in keys_to_del:
            del test_data[key]

        return errors

    @staticmethod
    def __validate_required(proto_fields, test_data):
        # type: (OrderedDict, dict) -> [str]
        errors = []

        for field_name, message_data in proto_fields.items():  # type: (str, MessageField)
            if message_data.is_required and field_name not in test_data:
                errors.append(
                    "field '%s [%s]' is required." % (field_name, message_data.type)
                )

        return errors

    def __validate_structure(self, proto_file, proto_scope, test_data, test_path, scope_name):
        # type: (ProtoFile, OrderedDict, dict, str, str) -> None
        # TODO: 'scope_name' only for one error. Need to find a way to avoid using it in args.
        if type(test_data) != dict:
            self.__add_errors(
                test_path,
                "expected structure [%s], got [%s] (as %r) instead."
                % (scope_name, type(test_data).__name__, test_data)
            )
            return

        proto_fields = proto_scope[ProtoFile.FIELDS_KEY]

        errors = self.__validate_and_del_excess(proto_fields, test_data)
        self.__add_errors(test_path, errors)

        errors = self.__validate_required(proto_fields, test_data)
        self.__add_errors(test_path, errors)

        for test_key, test_value in test_data.items():
            test_message = proto_fields[test_key]  # type: MessageField
            new_path = "%s > %s" % (test_path, test_key)  # type: str

            if test_message.is_repeated and type(test_value) != list:
                self.__add_errors(
                    new_path,
                    "expected array of [%s], got [%s]"
                    % (test_message.type, type(test_value).__name__)
                )
                continue

            if test_message.is_base_type:
                if test_message.is_repeated:
                    errors = self.__validate_multiply_base_types(test_message.type, test_value)
                else:
                    errors = self.__validate_base_type(test_message.type, test_value)

                self.__add_errors(new_path, errors)
                continue

            if test_message.is_map:
                # map can not be repeated
                errors = self.__validate_map_type(proto_file, test_message.type, test_value, new_path)
                self.__add_errors(new_path, errors)
                continue

            scoped_proto_type = None
            if test_message.type in proto_scope:
                scoped_proto_type = proto_scope[test_message.type]
            if test_message.type in proto_file.structure:
                scoped_proto_type = proto_file.structure[test_message.type]

            if isinstance(scoped_proto_type, EnumField):
                if test_message.is_repeated:
                    errors = self.__validate_multiply_enum_types(scoped_proto_type, test_value)
                else:
                    errors = self.__validate_enum_type(scoped_proto_type, test_value)

                self.__add_errors(new_path, errors)
                continue

            if scoped_proto_type:
                # WARN: -!- Recursive -!-
                if test_message.is_repeated:
                    self.__validate_multiply_structures(
                        proto_file, scoped_proto_type, test_value, new_path, test_message.type
                    )
                else:
                    self.__validate_structure(
                        proto_file, scoped_proto_type, test_value, new_path, test_message.type
                    )
                continue

            if proto_file.has_in_imports(test_message.type):
                new_proto_file = proto_file.get_import_package(test_message.type)
                new_proto_scope = proto_file.get_import_package_as_structure(test_message.type)

                # WARN: -!- Recursive -!-
                if test_message.is_repeated:
                    self.__validate_multiply_structures(
                        new_proto_file, new_proto_scope, test_value, new_path, test_message.type
                    )
                else:
                    self.__validate_structure(
                        new_proto_file, new_proto_scope, test_value, new_path, test_message.type
                    )
                continue

            print("[Something goes wrong] Sorry, but here's a bug. Can you fix it?")
            print("Path:", test_path, ". Field: ", test_key)

    def __validate_multiply_structures(self, proto_file, proto_scope, test_data, test_path, scope_name):
        # type: (ProtoFile, OrderedDict, dict, str, str) -> None
        for value in test_data:
            self.__validate_structure(proto_file, proto_scope, value, test_path, scope_name)

    def validate_json(self, proto_file, root_field_name, test_data):
        # type: (ProtoFile, str, dict) -> (bool, str)
        self.__errors = []

        proto_scope = proto_file.structure[root_field_name]
        self.__validate_structure(proto_file, proto_scope, test_data, root_field_name, root_field_name)

        return bool(self.__errors), self.__errors
