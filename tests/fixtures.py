import pytest


@pytest.fixture
def sf11meetinginfo():
    return {
        "id": "meetingInformation",
        "title": "Meeting Information",
        "$formkit": "group",
        "children": [
            {
                "key": "activity_type",
                "id": "activity_type",
                "name": "activity_type",
                "label": "$pgettext('activity_type', 'Meeting or Training')",
                "$formkit": "select",
                "placeholder": '$gettext("Please select")',
                "options": [{"value": "1", "label": "Training"}, {"value": "2", "label": "Meeting"}],
            },
            {
                "key": "activity_subtype",
                "id": "activity_subtype",
                "if": "$get(activity_type).value",
                "name": "activity_subtype",
                "label": "$pgettext('activity_type', 'Activity Type')",
                "$formkit": "select",
                "placeholder": '$gettext("Please select")',
                "options": "$getoptions.sf11.activitySubType($get(activity_type).value)",
            },
            {
                "$formkit": "datepicker",
                "name": "date",
                "id": "date",
                "key": "date",
                "label": '$gettext("Date")',
                "format": "DD/MM/YYYY",
                "valueFormat": "DD/MM/YYYY",
                "calendarIcon": "calendar",
                "nextIcon": "angleRight",
                "prevIcon": "angleLeft",
                "_currentDate": "$getCurrentDate",
                "sectionsSchema": {
                    "day": {
                        "children": [
                            "$day.getDate()",
                            {
                                "if": "$attrs._currentDate().day === $day.getDate()",
                                "children": [
                                    {
                                        "if": "$attrs._currentDate().month === $day.getMonth()",
                                        "children": [
                                            {
                                                "$el": "div",
                                                "if": "$attrs._currentDate().year === $day.getFullYear()",
                                                "attrs": {"class": "formkit-day-highlight"},
                                            }
                                        ],
                                    }
                                ],
                            },
                        ]
                    }
                },
            },
        ],
        "icon": "las la-info-circle",
    }


@pytest.fixture
def sf11():
    """
    This is the complete definition for 'SF 11' as at
    Aug 2023

    To recreate this
    >>> from formkit_python_sync.get_schemas import _run_tsx
    >>> import tempfile
    >>> import json
    >>> for form_defn in _run_tsx():
    >>>      import tempfile
    >>>      with tempfile.NamedTemporaryFile(prefix=form_defn['name'], delete=False, mode='w') as o:
    >>>          o.write(json.dumps(form_defn))
    >>>          print(o.name)
    """

    return [
        {
            "id": "meetingInformation",
            "title": "Meeting Information",
            "$formkit": "group",
            "children": [
                {
                    "key": "activity_type",
                    "id": "activity_type",
                    "name": "activity_type",
                    "label": "$pgettext('activity_type', 'Meeting or Training')",
                    "$formkit": "select",
                    "placeholder": '$gettext("Please select")',
                    "options": [{"value": "1", "label": "Training"}, {"value": "2", "label": "Meeting"}],
                },
                {
                    "key": "activity_subtype",
                    "id": "activity_subtype",
                    "if": "$get(activity_type).value",
                    "name": "activity_subtype",
                    "label": "$pgettext('activity_type', 'Activity Type')",
                    "$formkit": "select",
                    "placeholder": '$gettext("Please select")',
                    "options": "$getoptions.sf11.activitySubType($get(activity_type).value)",
                },
                {
                    "$formkit": "datepicker",
                    "name": "date",
                    "id": "date",
                    "key": "date",
                    "label": '$gettext("Date")',
                    "format": "DD/MM/YYYY",
                    "valueFormat": "DD/MM/YYYY",
                    "calendarIcon": "calendar",
                    "nextIcon": "angleRight",
                    "prevIcon": "angleLeft",
                    "_currentDate": "$getCurrentDate",
                    "sectionsSchema": {
                        "day": {
                            "children": [
                                "$day.getDate()",
                                {
                                    "if": "$attrs._currentDate().day === $day.getDate()",
                                    "children": [
                                        {
                                            "if": "$attrs._currentDate().month === $day.getMonth()",
                                            "children": [
                                                {
                                                    "$el": "div",
                                                    "if": "$attrs._currentDate().year === $day.getFullYear()",
                                                    "attrs": {"class": "formkit-day-highlight"},
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                },
            ],
            "icon": "las la-info-circle",
        },
        {
            "id": "location",
            "title": "Location",
            "$formkit": "group",
            "children": [
                {
                    "$formkit": "select",
                    "id": "district",
                    "name": "district",
                    "key": "district",
                    "label": "$gettext(Municipality)",
                    "options": "$getLocations()",
                },
                {
                    "$formkit": "select",
                    "id": "administrative_post",
                    "name": "administrative_post",
                    "key": "administrative_post",
                    "label": '$gettext("Administrative Post")',
                    "options": "$getLocations($get(district).value)",
                    "if": "$get(district).value && $get(activity_subtype).value !== '20'",
                },
                {
                    "$formkit": "select",
                    "id": "suco",
                    "name": "suco",
                    "key": "suco",
                    "label": "$gettext(Suco)",
                    "options": "$getLocations($get(district).value, $get(administrative_post).value)",
                    "if": "$get(administrative_post).value && $get(activity_subtype).value !== '20' && $get(activity_subtype).value !== '21'",
                },
                {
                    "$formkit": "select",
                    "id": "aldeia",
                    "name": "aldeia",
                    "key": "aldeia",
                    "label": "$gettext(Aldeia)",
                    "options": "$getLocations($get(district).value, $get(administrative_post).value, $get(suco).value)",
                    "if": "$get(suco).value && $get(activity_type).value !== '1' && $get(activity_subtype).value !== '20' && $get(activity_subtype).value !== '21' && $get(activity_subtype).value !== '1' && $get(activity_subtype).value !== '24' && $get(activity_subtype).value !== '4' && $get(activity_subtype).value !== '11' && $get(activity_subtype).value !== '16' && $get(activity_subtype).value !== '17' && $get(activity_subtype).value !== '28'",
                },
            ],
            "icon": "las la-map-marked-alt",
        },
        {
            "id": "participants",
            "title": "Participants",
            "$formkit": "group",
            "children": [
                {
                    "key": "attendance_male",
                    "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 40 && $get(activity_subtype).value != 11",
                    "id": "attendance_male",
                    "name": "attendance_male",
                    "label": "$pgettext('partisipants', 'Total participants male')",
                    "validation": "greaterThanOrEqualSum:kpa_male+community_member_male",
                    "validation-messages": {
                        "greaterThanOrEqualSum": '$gettext("The total participants male should be greater than or equal to the sum of Participants Suku Management Team (SMT) - male and Number of community members - male")'
                    },
                    "$formkit": "number",
                    "min": 0,
                },
                {
                    "key": "attendance_female",
                    "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 11",
                    "id": "attendance_female",
                    "name": "attendance_female",
                    "label": "$pgettext('partisipants', 'Total participants female')",
                    "validation": "greaterThanOrEqualSum:kpa_female+community_member_female",
                    "validation-messages": {
                        "greaterThanOrEqualSum": '$gettext("The total participants female should be greater than or equal to the sum of Participants Suku Management Team (SMT) - female and Number of community members - female")'
                    },
                    "$formkit": "number",
                    "min": 0,
                },
                {
                    "key": "kpa_male",
                    "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 20 && $get(activity_subtype).value != 21 && $get(activity_subtype).value != 40 && $get(activity_subtype).value != 11",
                    "id": "kpa_male",
                    "name": "kpa_male",
                    "label": "$pgettext('partisipants', 'Participants Suku Management Team (SMT) - male')",
                    "$formkit": "number",
                    "min": 0,
                },
                {
                    "key": "kpa_female",
                    "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 11 && $get(activity_subtype).value != 20 && $get(activity_subtype).value != 21",
                    "id": "kpa_female",
                    "name": "kpa_female",
                    "label": "$pgettext('partisipants', 'Participants Suku Management Team (SMT) - female')",
                    "$formkit": "number",
                    "min": 0,
                },
                {
                    "key": "disable_male",
                    "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 40 && $get(activity_subtype).value != 11",
                    "id": "disable_male",
                    "name": "disable_male",
                    "label": "$pgettext('partisipants', 'Number of People with Disability - male')",
                    "$formkit": "number",
                    "min": 0,
                },
                {
                    "key": "disable_female",
                    "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 11",
                    "id": "disable_female",
                    "name": "disable_female",
                    "label": "$pgettext('partisipants', 'Number of People with Disability - female')",
                    "$formkit": "number",
                    "min": 0,
                },
                {
                    "key": "community_member_male",
                    "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 20 && $get(activity_subtype).value != 21 && $get(activity_subtype).value != 40 && $get(activity_subtype).value != 11",
                    "id": "community_member_male",
                    "name": "community_member_male",
                    "label": "$pgettext('partisipants', 'Number of community members - male')",
                    "$formkit": "number",
                    "min": 0,
                },
                {
                    "key": "community_member_female",
                    "if": "$get(activity_type).value !== '----' && $get(activity_subtype).value !== '----' && $get(activity_subtype).value != 16 && $get(activity_subtype).value != 11 && $get(activity_subtype).value != 20 && $get(activity_subtype).value != 21",
                    "id": "community_member_female",
                    "name": "community_member_female",
                    "label": "$pgettext('partisipants', 'Number of community members - female')",
                    "$formkit": "number",
                    "min": 0,
                },
            ],
            "icon": "las la-users",
        },
    ]


@pytest.fixture
def tf_13_2_1():
    return {
        "$formkit": "group",
        "name": "TF_13_2_1",
        "children": [
            {
                "$formkit": "select",
                "id": "district",
                "name": "district",
                "key": "district",
                "label": "$gettext(Municipality)",
                "options": "$getLocations()",
            },
            {
                "$formkit": "select",
                "id": "administrative_post",
                "name": "administrative_post",
                "key": "administrative_post",
                "label": '$gettext("Administrative Post")',
                "options": "$getLocations($get(district).value)",
                "if": "$get(district).value",
            },
            {
                "$formkit": "datepicker",
                "name": "date",
                "id": "date",
                "key": "date",
                "label": '$gettext("Date")',
                "format": "DD/MM/YYYY",
                "calendarIcon": "calendar",
                "nextIcon": "angleRight",
                "prevIcon": "angleLeft",
                "_currentDate": "$getCurrentDate",
                "sectionsSchema": {
                    "day": {
                        "children": [
                            "$day.getDate()",
                            {
                                "if": "$attrs._currentDate().day === $day.getDate()",
                                "children": [
                                    {
                                        "if": "$attrs._currentDate().month === $day.getMonth()",
                                        "children": [
                                            {
                                                "$el": "div",
                                                "if": "$attrs._currentDate().year === $day.getFullYear()",
                                                "attrs": {"class": "formkit-day-highlight"},
                                            }
                                        ],
                                    }
                                ],
                            },
                        ]
                    }
                },
            },
            {
                "$formkit": "select",
                "name": "month",
                "label": '$gettext("Month")',
                "options": [
                    {"value": 1, "label": "January"},
                    {"value": 2, "label": "February"},
                    {"value": 3, "label": "March"},
                    {"value": 4, "label": "April"},
                    {"value": 5, "label": "May"},
                    {"value": 6, "label": "June"},
                    {"value": 7, "label": "July"},
                    {"value": 8, "label": "August"},
                    {"value": 9, "label": "September"},
                    {"value": 10, "label": "October"},
                    {"value": 11, "label": "November"},
                    {"value": 12, "label": "December"},
                ],
                "placeholder": '$gettext("Select month")',
            },
            {
                "$formkit": "select",
                "name": "year",
                "label": '$gettext("Year")',
                "options": [2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023],
                "placeholder": '$gettext("Select year")',
            },
            {
                "$formkit": "repeater",
                "addLabel": '$gettext("Add project")',
                "upControl": False,
                "downControl": False,
                "name": "repeaterProjectProgress",
                "itemsClass": "repeater",
                "itemClass": "repeater-children-index",
                "min": 1,
                "id": "repeaterProjectProgress",
                "removeLabel": '$gettext("Remove")',
                "removeAction": "$repeaterRemoveAction",
                "sectionsSchema": {
                    "remove": {
                        "children": [
                            {
                                "$el": "button",
                                "if": "$value.length > 1",
                                "attrs": {
                                    "data-index": "$index",
                                    "data-repeaterid": "$id",
                                    "onClick": "$attrs.removeAction",
                                    "class": "disabled:hidden cursor-pointer flex items-center justify-center flex-row-reverse h-[50px] rounded-2.5xl px-4 w-full bg-white border-2 border-solid border-emerald-600 text-zinc-900 hover:bg-emerald-600 hover:text-white font-bold text-base",
                                },
                                "children": ["$attrs.removeLabel"],
                            }
                        ]
                    }
                },
                "children": [
                    {
                        "$el": "div",
                        "children": ['$gettext("project")', " ", {"$el": "span", "children": ["$: ($index + 1)"]}],
                        "attrs": {"class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"},
                    },
                    {
                        "key": "$: (sukus + $index)",
                        "name": "suco",
                        "label": '$gettext("Suku")',
                        "placeholder": '$gettext("Select one")',
                        "formkit": "select",
                        "$formkit": "select",
                        "options": "$getLocations($get(district).value, $get(administrative_post).value)",
                        "id": "$: (sukus + $index)",
                    },
                    {
                        "$formkit": "select",
                        "label": '$gettext("Project name")',
                        "key": "project_name",
                        "placeholder": '$gettext("Please select")',
                        "options": "$getoptions.tf1321.outputs($get(district).value, $get(administrative_post).value, $get(sukus + $index).value)",
                        "name": "project_name",
                        "id": "project_name",
                    },
                    {
                        "$formkit": "number",
                        "label": "Total (%)",
                        "placeholder": '$gettext("Please enter")',
                        "name": "total",
                        "min": "0",
                        "max": "100",
                        "validation": "shouldNotAcceptNegativeValue",
                    },
                ],
            },
        ],
    }
