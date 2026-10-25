"""The sync feeds return changes in the order they happened (asked for by Partisipa's compat run).

Without an ORDER BY the rows come back in storage order, which is correct but cannot be
diffed or snapshot-tested across two databases holding the same data.
"""

import pytest

from formkit_ninja import models


@pytest.mark.django_db
def test_list_nodes_comes_back_in_change_order():
    nodes = [models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "text", "name": f"f{i}"}) for i in range(5)]
    # Re-save the middle node so its change number is now the highest.
    nodes[2].save()
    query = models.FormKitSchemaNode.objects.from_change(-1)
    assert query.query.order_by == ("track_change",), "the node feed must carry an explicit order"
    changes = [n.track_change for n in query]
    assert changes == sorted(changes)
    assert changes[-1] == models.FormKitSchemaNode.objects.get(pk=nodes[2].pk).track_change


@pytest.mark.django_db
def test_list_related_nodes_comes_back_in_change_order():
    parent = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "group", "name": "g"})
    for i in range(3):
        child = models.FormKitSchemaNode.objects.create(node_type="$formkit", node={"$formkit": "text", "name": f"c{i}"})
        models.NodeChildren.objects.create(parent=parent, child=child, order=i)
    query = models.NodeChildren.objects.aggregate_changes_table()
    assert query.query.order_by == ("latest_change",), "the relations feed must carry an explicit order"
    latest = [r.latest_change for r in query]
    assert latest == sorted(latest)
