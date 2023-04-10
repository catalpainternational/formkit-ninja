# Administration Tutorial

The FormKit "admin" page has a number of changes to help adding new components, including support for JSON and translated fields.

In this tutorial, we will
 - Create a simple FormKit date note
 - Verify that we can serialize it and retrieve it through the API

## Adding a New Formkit Node

Most forms are defined as "FormKit" nodes.

To add a simple 'date' node:

 - Open the "admin/" page to [http://localhost:8000/admin/formkit_ninja/formkitschemanode/](http://localhost:8000/admin/formkit_ninja/formkitschemanode/) (change the server URL if required)
 - Click "Add Form Kit Schema Node"

You'll see a small form with the initial "node type" and "description" fields.

### Setting the Node Type

Most of the data we pass to the frontend is 'FormKit nodes'. It's also possible to add "components" and "elements". First choose "FormKit" as the node type.

Enter the following:

| FIeld | value |
|---|---|
|Node type | "Formkit" |
|Description | "This is my Date Node" |

Click "Save and Continue Editing"

### Add Additional Options

Now you should see additional options

| Field | Value|
|---|---|
| Formkit | date |
|Name | "date" |

Now if you check the database, you ought to have the `FormKitSchemaNode` in the database

```
>>> FormKitSchemaNode
<class 'formkit_ninja.models.FormKitSchemaNode'>
>>> FormKitSchemaNode.objects.first()
<FormKitSchemaNode: FormKitSchemaNode object (b0fc2155-8bb1-419c-b628-0dc994226403)>
>>> FormKitSchemaNode.objects.first().node
{'formkit': 'date', 'description': 'Date', 'name': 'date'}
>>> FormKitSchemaNode.objects.first().label
{'tet': 'data', 'en': 'date'}
>>> FormKitSchemaNode.objects.first().id
UUID('b0fc2155-8bb1-419c-b628-0dc994226403')
```

### Processing Your Node

This can be transformed into a Pydantic object 

```
>>> FormKitSchemaNode.objects.first().get_node()
FormKitNode(__root__=DateNode(children=None, key=None, if_condition=None, for_loop=None, bind=None, meta=None, html_id=None, name='date', label='date', help=None, validation=None, validationLabel=None, validationVisibility=None, validationMessages=None, placeholder=None, value=None, prefixIcon=None, classes=None, node_type='formkit', formkit='date', dollar_formkit='date'))
```

And a valid JSON object

```
>>> FormKitSchemaNode.objects.first().get_node().json(exclude_none=True)
'{"name": "date", "label": "date", "node_type": "formkit", "formkit": "date", "dollar_formkit": "date"}'
```

### Check The API

My node has a UUID of `b0fc2155-8bb1-419c-b628-0dc994226403`

I can check that I can fetch it from the API at

`http://localhost:8002/api/formkit/node/b0fc2155-8bb1-419c-b628-0dc994226403`



