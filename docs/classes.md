# Classes

Formkit-Ninja exposes the following classes:


``` mermaid
classDiagram
    FormKitSchemaNode "1" <-- "0..1" Option:field
    FormComponents "0..1" <-- "1" FormKitSchema:schema
    FormComponents "0..1" <-- "1" FormKitSchemaNode:node
    Membership "0..1" <-- "1" FormKitSchemaNode:group
    Membership "0..1" <-- "1" FormKitSchemaNode:member
    NodeChildren  "0..1" <-- "1" FormKitSchemaNode:parent
    FormKitSchemaNode "0..1" <-- "1" Membership:group
    FormKitSchemaNode "0..1" <-- "1" Membership:children
    FormKitSchema "0..1" <-- "1" FormComponents
    class OptionDict {
        +String value
        +String label
    }
    class Option {
        +String value
        +String label
        +int order 
        +from_pydantic()
    }
    class FormComponents{
        +int order 
    }
    class Membership{
        +int order 
    }
    class FormKitSchemaNode{
        +String node_type
        +String description
        +String id
        +String label
        +String placeholder
        +String help
        +String node
        
        + get_node_values()
        + get_node()
        + save()
        - from_pydantic()
    }
    class FormKitSchema {
        +String name
        +String properties
        +get_schema_values()
        +to_pydantic()
        -FormKitSchema from_pydantic()
        -from_json()
    }
```

::: formkit_ninja.models