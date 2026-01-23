# FormKit Feature Matrix

This document outlines the support status of various FormKit inputs within `formkit-ninja` compared to the official FormKit documentation.

## Core Inputs

| Input Type | Supported | Notes |
| :--- | :---: | :--- |
| `text` | ✅ | |
| `textarea` | ✅ | |
| `number` | ✅ | |
| `select` | ✅ | |
| `checkbox` | ✅ | |
| `radio` | ✅ | |
| `password` | ✅ | |
| `email` | ✅ | |
| `tel` | ✅ | |
| `hidden` | ✅ | |
| `date` | ✅ | Native HTML date input |
| `url` | ⚠️ | Use `text` or `additional_props` |
| `color` | ⚠️ | Use `text` or `additional_props` |
| `time` | ⚠️ | Use `text` or `additional_props` |
| `file` | ⚠️ | Not explicitly typed |

## Pro / Synthetic Inputs

| Input Type | Supported | Notes |
| :--- | :---: | :--- |
| `repeater` | ✅ | Custom implementation aligned with Pro |
| `datepicker` | ✅ | Custom implementation aligned with Pro |
| `autocomplete` | ✅ | |
| `dropdown` | ✅ | |
| `currency` | ✅ | |
| `group` | ✅ | |
| `mask` | ❌ | |
| `rating` | ❌ | |
| `slider` | ❌ | |
| `taglist` | ❌ | |
| `transfer-list` | ❌ | |
| `toggle` | ❌ | |

## Custom Inputs

| Input Type | Description |
| :--- | :--- |
| `uuid` | Generates a UUID field. |
