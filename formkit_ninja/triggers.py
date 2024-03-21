import pgtrigger

NODE_CHANGE_ID = "formkitschemanode_change_id"
NODE_CHILDREN_CHANGE_ID = "nodechildren_change_id"


def create_sequence(sequence_name: str):
    return f"CREATE SEQUENCE IF NOT EXISTS {sequence_name};"


def drop_sequence(sequence_name: str):
    return f"DROP SEQUENCE IF EXISTS {sequence_name};"


def create_sequence_migration(sequence_name: str):
    return (create_sequence(sequence_name), drop_sequence(sequence_name))


def update_group_trigger(order_by_field: str, id_field: str = "id"):
    """
    Takes a model with an "order" field and
    a "group" field and adds a trigger to
    keep the ordering correct
    This assumes a pk field named "id" too
    """
    return pgtrigger.Trigger(
        name="order_on_update_option",
        when=pgtrigger.After,
        operation=pgtrigger.Update,
        func=pgtrigger.Func(
            f"""
                -- Do not allow a "null" value
                -- This stops Django from dumbly updating
                -- which can break the trigger
                if NEW."order" IS NULL then
                    NEW."order" = OLD."order";
                end if;
                if NEW."order" > OLD."order" then
                    update {{meta.db_table}}
                    set "order" = "order"- 1
                    where "order" <= NEW."order"
                    and "order" > OLD."order"
                    and "{order_by_field}" = NEW."{order_by_field}"
                    and "{id_field}" <> NEW."{id_field}";
                else
                    update {{meta.db_table}}
                    set "order" = "order"+ 1
                    where "order" >= NEW."order"
                    and "order" < OLD."order"
                    and "{order_by_field}" = NEW."{order_by_field}"
                    and "{id_field}" <> NEW."{id_field}";
                end if;
                RETURN NEW;
        """
        ),
        condition=pgtrigger.Condition("pg_trigger_depth() = 0"),  # Prevents infinite recursion
    )


def insert_group_trigger(order_by_field: str):
    return pgtrigger.Trigger(
        name="order_on_insert_option",
        when=pgtrigger.Before,
        operation=pgtrigger.Insert,
        func=pgtrigger.Func(
            f'NEW."order" = (SELECT coalesce(max("order"), 0) + 1 FROM {{meta.db_table}} WHERE {{meta.db_table}}."{order_by_field}" = NEW."{order_by_field}"); RETURN NEW;'
        ),
    )


def update_or_insert_group_trigger(order_by_field: str, id_field: str = "id"):
    return [update_group_trigger(order_by_field, id_field), insert_group_trigger(order_by_field)]


def bump_sequence_value(value_field: str = "track_change", sequence_name: str = NODE_CHANGE_ID):
    """
    Increment a sequence value and set the field referred to to that value.
    Intended to track latest changes across a model / multiple models
    to make syncing easier
    Remember to add the appropriate "CREATE SEQUENCE" code to a migration.
    That would be something like

    migrations.RunSQL(
        '''
        CREATE SEQUENCE IF NOT EXISTS ida_options_version_seq;
        ''',
        '''
        DROP SEQUENCE IF EXISTS ida_options_version_seq;
        ''',
    )
    """
    return pgtrigger.Trigger(
        name="version_on_update",
        when=pgtrigger.Before,
        operation=pgtrigger.Update | pgtrigger.Insert,
        func=f"""NEW."{value_field}" = nextval('{sequence_name}'); RETURN NEW;""",
    )
