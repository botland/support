# Console — Configuration

The **Configuration** page is for backup and recovery of appliance settings.

## Export

Download **conf.json** — a portable snapshot of cluster and deployment configuration (including head identity fields used after head migration).

## Import

Paste or load a configuration document to restore settings. Invalid JSON is rejected with an error.

## USB recovery

For field recovery, place `conf.json` on a USB dongle in the appliance’s designated mount location. The appliance copies updated configuration into place when the media changes. This supports disaster recovery without depending on a cloud console.
