# Adressänderung nach Bestellung

Das Diagramm ist ein konzeptioneller Integrationsentwurf, kein Nachweis bereits implementierter Shop-/Lager-/Carrier-APIs. Drei verknüpfte Abschnitte halten die PDF in normaler A4-Ansicht lesbar: Berechtigung, sichere Änderung vor Versand und Umleitung nach Übergabe. Mermaid und Vektorgrafik werden aus derselben Knoten-/Kantendefinition erzeugt; die SVG/PDF verwenden ein eigenes Layout, keinen Mermaid-Renderer.

## Ablauf

Die Plattform nimmt die Anfrage idempotent entgegen, verifiziert Bestellung und Berechtigung und prüft Zustellgebiet sowie Geschäftsregeln. Unbekannte Bestellungen und nicht berechtigte Anfragen bekommen neutrale Rückmeldungen ohne fremde Bestelldaten. Ungültige Adressen brauchen Korrektur; zusätzliche Kosten oder riskante Änderungen Supportprüfung. Bei nicht verfügbarer OMS/WMS-Schnittstelle wird kein Erfolg gemeldet.

Vor Übergabe muss das WMS einen bedingten Versand-Hold tatsächlich bestätigen. Dieser muss auch Labelgenerierung, Label-Neudruck und ausstehende Versandjobs blockieren. Unter diesem Hold wird der Zustand erneut geprüft. Das OMS schreibt Adresse, Version, Outbox-Ereignis und Audit in einer Transaktion mit Versionsbedingung. WMS und Plattform bestätigen die neue Adresse und Version; ein früheres Label wird kontrolliert invalidiert und ersetzt. Erst danach wird der Hold freigegeben und der Kunde erhält eine Erfolgsnachricht.

Nach Carrier-Übergabe ist eine reine OMS-Adressänderung wirkungslos. Es wird eine unterstützte Umleitung angefragt. Eine bestätigte neue Zieladresse wird separat im OMS dokumentiert; die ursprüngliche Versandhistorie bleibt erhalten. Ablehnung, ausstehende Carrier-Prüfung, Timeout oder Schreibfehler werden an Support übergeben. Webhooks müssen authentifiziert, dedupliziert und gegen die korrekte Auftrags-/Versionsreferenz geprüft werden.

## Wahrscheinlichster operativer Fehler

Während die Plattform noch die neue Adresse speichert, erzeugt das Lager ein Versandlabel mit der alten Adresse. Der Kunde bekommt „geändert“, aber das Paket geht trotzdem an die alte Anschrift. Ein einmaliger Statuscheck verhindert das nicht: zwischen Lesen und Schreiben kann Fulfillment fortschreiten.

Eine reale WMS-Sperre, erneute Zustandsprüfung, Compare-and-swap, idempotente Übergaben und Bestätigungen aller erforderlichen Systeme reduzieren dieses Risiko. Ohne eine von ALLEN Versandjobs respektierte Sperre ist der automatische Vor-Versand-Pfad nicht sicher; dann muss Support das Fulfillment stoppen oder die Änderung ablehnen. Ein Erfolgscode einer einzelnen API ist kein Beleg für systemweite Konsistenz.

## Grenzen und Recovery

Es gibt keine globale ACID-Transaktion über OMS, WMS und Carrier. Die Outbox verhindert verlorene Übergaben; Versionsreferenzen verhindern veraltete Bestätigungen. Idempotenzschlüssel sind an Kunde, Bestellung und Änderungsinhalt gebunden; gleiche ID mit anderem Inhalt wird abgelehnt. Das OMS bleibt vor Versand führend für die bestellte Adresse; nach Übergabe bestätigt der Carrier die tatsächliche Umleitung.

Retries sind begrenzt. Unklare Ergebnisse werden vor einer erneuten Mutation über Statusabfragen abgeglichen. Ein fehlgeschlagener Benachrichtigungsversand wiederholt nur die Nachricht, nicht die Adressänderung. Bei partieller Synchronisation Hold behalten/Versand stoppen, Support benachrichtigen und dem Kunden „in Prüfung“ melden. WMS-Sperren dürfen nicht unbemerkt ablaufen: ein Ablauf muss Versand weiterhin verhindern oder als Alarm eskalieren. Nicht blind auf eine alte Adresse zurückrollen, wenn inzwischen schon ein Paket übergeben wurde.

Support dokumentiert die geprüfte Lösung oder Ablehnung, bestätigt den endgültigen Zustand und schließt den Auditvorgang. Es wird keine bedingungslose Erfolgsgarantie suggeriert. Geschäftsregeln für Abgaben, Zahlungen und Betrugsprüfung müssen mit dem jeweiligen Shop abgestimmt werden.
