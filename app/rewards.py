"""Zentrale Regeln fuer das Belohnungspunkte-System (AP10).

Punkte werden bewusst NICHT beim Anbieten oder Benachrichtigen vergeben, sondern erst
wenn die wartende Person tatsaechlich einen Ladevorgang am selben Ladepunkt startet.
Das verhindert, dass Nutzer Punkte "faken" koennen, ohne den Platz wirklich zu raeumen.
"""

from app.models.models import ParkingOfferType

POINTS_BY_OFFER_TYPE: dict[ParkingOfferType, int] = {
    ParkingOfferType.FREE: 15,
    ParkingOfferType.PAID: 8,
    ParkingOfferType.NONE: 3,
}


def points_for_offer(offer: ParkingOfferType) -> int:
    return POINTS_BY_OFFER_TYPE.get(offer, 0)
