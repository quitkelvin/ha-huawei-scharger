# Huawei SCharger (FusionSolar) for Home Assistant

Custom integration that reads and controls a **Huawei SCharger** wallbox through the
**FusionSolar web portal** – the same way the portal's own charger page does.

> ## DISCLAIMER
> This is an **independent hobby project**. It is **not affiliated with, endorsed by or
> supported by Huawei**. "Huawei", "FusionSolar" and "SCharger" are trademarks of their
> respective owners and are used here only to describe compatibility.
>
> The integration uses the **unofficial, undocumented web API** of the FusionSolar portal.
> It can change or stop working at any time without notice. Settings changed through this
> integration are written to your real wallbox.
>
> **Use at your own risk. No warranty, no liability** for any damage, costs, lost charging
> sessions or account restrictions (see LICENSE).
>
> **Tip:** create a **separate FusionSolar user** for Home Assistant (read-only if you only
> need sensors). Logging in with the same user in parallel (app, browser, Home Assistant)
> logs the other sessions out and can trigger captcha prompts.

## Features

Device **Huawei SCharger** (first wallbox and its first charging connector of the plant):

| Type | Entities |
|---|---|
| Sensors | charging power (kW), status (`charging` / `idle`), total energy charged (kWh, `total_increasing`), vehicle / working status, working mode (reported), connector lock, phase currents L1–L3, temperature, dynamic charging power, maximum charging power, data timestamp, reported status (disabled by default) |
| Select | working mode (`normal` / `pv_preferred`), connector locking mode (`always` / `while_charging` / `after_plug_in`) |
| Number | dynamic power limit (kW), maximum charging current (A), grid power in PV mode (kW), surplus start threshold (kW) |
| Switch | dynamic charging power on/off, automatic phase switching |

Selects, numbers and switches are only created when a charging connector exists. After a
change the written value is shown until the portal confirms it on read-back (at most 3
minutes); the settings are re-read on every poll while a change is pending.

Device **FusionSolar plant**: CO2 avoided (kg), standard coal saved (kg), equivalent trees
planted (refreshed every 30 minutes).


### Start / stop charging

FusionSolar has no documented remote start/stop command. In practice the working mode does the job:
- **PV power preferred** stops charging from grid/battery – without solar surplus the charger waits ("PV Power Waiting").
- **Normal charge** starts charging at full power (grid/battery included) when a car is connected.

Tested: switching to *Normal charge* started charging within about a minute, switching back stopped it immediately.

## Installation

1. HACS → Custom repositories → add `https://github.com/quitkelvin/ha-huawei-scharger`
   (category *Integration*), install, restart Home Assistant.
   Manual: copy `custom_components/huawei_scharger` into your `config/custom_components`.
2. Settings → Devices & services → Add integration → **Huawei SCharger (FusionSolar)**.
3. Enter username, password and the portal host of your region (default
   `eu5.fusionsolar.huawei.com`). If the account has several plants, pick the one with the
   wallbox.

Options: polling interval (default 60 s, minimum 30 s).

## Login, session expiry and captcha

The session is renewed automatically when it expires. If FusionSolar asks for a captcha,
the integration cannot solve it: it stops and asks for re-authentication. Log in once in a
browser with that user, wait a few minutes, then re-authenticate in Home Assistant.

## Limitations

- Only the first wallbox and its first connector of a plant are used.
- Values come from the cloud portal, not from the wallbox directly; they can lag behind.
- Signal ids and endpoints were derived from the portal's web page and may differ for other
  firmware versions.

## Deutsch (Kurzfassung)

Inoffizielle Home-Assistant-Integration für die **Huawei SCharger** Wallbox über das
**FusionSolar-Webportal**. Unabhängiges Hobbyprojekt, **nicht von Huawei** unterstützt oder
autorisiert; Marken gehören ihren Inhabern. Die Web-API ist inoffiziell und kann sich
jederzeit ändern. **Nutzung auf eigene Gefahr, keine Haftung.**

Empfehlung: einen **eigenen FusionSolar-Benutzer** für Home Assistant anlegen, da sich
parallele Anmeldungen mit demselben Benutzer gegenseitig abmelden.

Funktionen: Ladeleistung, Status, Geladen gesamt, Fahrzeug, Ströme L1–L3, Temperatur,
dynamische und maximale Ladeleistung, Datenstand; Lademodus und Verriegelungsmodus (Auswahl);
max. dynamische Leistung, max. Ladestrom, Netzanteil im PV-Modus, Überschuss-Startschwelle
(Zahlen); dynamische Ladeleistung und Phasenumschaltung (Schalter); dazu CO2-Einsparung,
eingesparte Standardkohle und gepflanzte Bäume der Anlage. Einrichtung über
Einstellungen → Geräte & Dienste; Oberfläche auf Deutsch und Englisch.

## NOTICE

Login code adapted from Home-Assistant-FusionSolar-App by Henrique Craveiro, MIT
(https://github.com/hcraveiro/Home-Assistant-FusionSolar-App). See LICENSE.

## License

MIT – see [LICENSE](LICENSE).

Third-party license texts: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
