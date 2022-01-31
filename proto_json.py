from collections import OrderedDict

from .proto_manager import MessageField, EnumField, ProtoFile, \
    STRING_TYPES, INT_TYPES, BOOL_TYPES, FLOAT_TYPES


class ProtoJson:
    def __init__(self):
        pass

    def __get_import_package_as_object(self, proto_file, field_type):
        # type: (ProtoFile, str) -> OrderedDict
        # 'interface.Button' -> ['interface', 'Button']
        package, message = field_type.split('.', 1)
        pkg = proto_file.imports[package]  # type: ProtoFile
        return self.as_object(pkg, message)

    @staticmethod
    def __get_default_value_for_field(field):
        # type: (MessageField) -> ...
        if field.type in STRING_TYPES:
            return 'String' if field.is_required else 'Optional string'

        elif field.type in INT_TYPES:
            return 100 if field.is_required else 50

        elif field.type in FLOAT_TYPES:
            return 100.5 if field.is_required else 50.25

        elif field.type in BOOL_TYPES:
            return field.is_required

    @staticmethod
    def __get_default_value_for_enum(enum_field, field):
        # type: (EnumField, MessageField) -> ...
        if enum_field.values:
            # Using first element from enum for example just because.
            return enum_field.values[0]
        else:
            return 'Enum' if field.is_required else 'Optional enum'

    def __get_object(self, proto_file, structure_field):
        # type: (ProtoFile, ...) -> OrderedDict
        result = OrderedDict()

        for field_name, field in structure_field[ProtoFile.FIELDS_KEY].items():  # type: (str, MessageField)
            default_value = self.__get_default_value_for_field(field)
            if default_value is not None:
                result[field_name] = default_value

            elif proto_file.has_in_imports(field.type):
                result[field_name] = self.__get_import_package_as_object(proto_file, field.type)

            else:
                next_field = None

                # Some types are not default and not from imports.
                # They were declared somewhere else in that scope.
                if field.type in structure_field:
                    next_field = structure_field[field.type]
                elif field.type in proto_file.structure:
                    next_field = proto_file.structure[field.type]

                is_message_field = isinstance(next_field, MessageField)
                is_enum_field = isinstance(next_field, EnumField)

                if next_field is not None and not is_message_field and not is_enum_field:
                    # WARN: -!- Recursive -!-
                    result[field_name] = self.__get_object(proto_file, next_field)

                elif is_enum_field:
                    result[field_name] = self.__get_default_value_for_enum(next_field, field)

                else:
                    result[field_name] = {}

            if field.is_repeated:
                result[field_name] = [result.get(field_name)]

        return result

    def as_object(self, proto_file, root_field_name):
        # type: (ProtoFile, str) -> OrderedDict
        scope = proto_file.structure[root_field_name]
        result = self.__get_object(proto_file, scope)
        return result
