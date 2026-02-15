#!/usr/bin/env python3
"""
Compare the user's English-Woccon source list (from Drive doc) to drive_staging/English-Woccon.json.
Reports entries that appear in the source but are missing from the staging extraction.
"""
import json
import re
from pathlib import Path

# Source: main list from the user's paste (English= woccon or English= woccon (pron))
# Lines that are clearly word entries; skip "same as above", section headers, vowel list, URLs.
SOURCE_ENTRIES = """
Acorns= roosome
Afraid= reheshiwau
A little while ago= yauka
All/That's all= cuttaune
Alligator= monwittetau
Alone/Leave it alone= sauhau
Angry= roocheha
Are you good?= Morene
Arrow= wą'se
Axe= tau unta winnik
Bag= ekoocromon
Ball Knock (game)= wap-ka-hare
Basket= rookeppa
Bear= nomme
Bear skin= Ounka
Bead= rummaen
Belt= wee kau
Big= itte
Big Stone= itte terraugh
Bitter= se
Black= yah-testea
Blankets= ruyú:ne:?
Blowing= hor
Blue= yah-testea
Boat= watt
Bottle= wattape
Boulder= itte terraugh
Bowl= cotsoo
Box= yopoonitsa
Bread= ikettau
Breeches= rooyaukitte
Broken in two= kitte
Brother= yenrauhe
Buckskin= rookau
Burl= wonne
Button= rummissauwoune
Made by hand= ru-/roo-
Bye= cuttau
Canoe= watt
Chert= wonsh-shee
Chew= raute
Clam= tsaure
Coat= rummissau
Cockles= tsaure
Comb= sacketoome posswa
Come along= quaute
Cord= wee-kau
Corn= cose
Cow= nappinjure
Crab= wunneau
Cubit= ishewounaup
Day= waukhaway
Dead= caure
Dog= taus-se
Dress= rhiieyau
Drunk= nonnupper
Duck= welka
Eat= eraute
Eight= nupsau
Eleven= tonne hauk sea
Englishman= wintsohore
Excel at= more
Eye= neetooh
Fart= pautyau
Fat= yendare
Fawn skin= witso
Feathers= soppe
Fever= waurepa
Finely formed= somme
Fire= yau
Fish= yacunne
Fishgig= weetipsa
Fist= wonne
Five= webtau
Flap= rhiieyau
Flints= matt-teer
Foot= epu
Fort= woccocon
Four= punnum-punne
Fox-skin= hannatockore
Give it to me= mothei
Go= Mei
Go you= yuppa mei
Goat= rumminshau
Good= mo
Good at= more
Goodbye= cuttau
Goose= auhuan
Got anything= eraute
Gourd= wattape
Grandmother= yicau
Grass= hauk
Gray= too-she
Green (moss)= itto
Gun= wittape
Gunlock= noonkosso
Gunpowder= rooeyaw
Hair= tumme
Hard= itte-teraugh
Hat= intome-posswa
He is= -re
He is a= hore
Head= poppe
Hello= tanake
Hers= wa
Hickory nuts= nimmia
His= wa
History= aucummato
Hoe= rope-pau
Hominy= roocauwa
Horse= yenwetoa
House= suuke
How many= tontarinte
In the= pa
Indians= yauh-he
Its= wa
Kettle= tooseawau
King= roamore
Knife= wee
Knot= wonne
Lazy= tontaunete
Leave it alone= sauhau
Leg= yau-huk
Lightwood= sek
Little= to
Loblolly (literally Spear Tree)= yupwaure
Loblolly pine= yupwaure
Place of the Loblolly pine= yupwauremau
Louse= eppesyau
Mad= rockcumne
Made= somme
Man= he
Manufactured items= ru-/roo-
Mat= soppepepor
Mink= soccon
Moon= wittapare
More than= soone
Mortar= wossoo
Moss= itto
Mouth Harp= wottiyau
Needle= wonsh-shee
Night= yantoha
Nine= wechere
Old Woman= yicau
On top= soppe
On top of= sacke
One= tonne
Otter= wetkes
Paint= whooyeonne
Panther= watta
Panther skin= wattau
Path= yauh
Peaches= yonne
Peak/Wampum= ettoco
Peas= coosauk
Person-genuine= Ya-
Pestle= miyau
Pig= nommewarraupau
Pine tree= hooheh
Place/Place of= mau
Plus= hauk
Pot= toos
Potatoes= wauti
Powerful= wacca
Queen= yicauau roamore
Questioning mode marker= -ne
Raccoon= auher
Rain= yawowa
Rat= wittau
Raw undressed skins= Teep
Red= yauta
Reed= weekwonne
Relatives= yauh-he
Remember it= aucummato
River= seunne
Riverbank= Ranbee
Road= yauh
Roanok (wampum bead/bead)= rummaen
Root= wauti
Rope= trauhe
Rum= yup se
Runlet (tree lined river)= yupyupseunne
Sacred= woccocock
Scissors= toc koor
Seven= nomis sau
She= rum-yup
Shirt= tacca pitteneer
Shoes= wee kessoo
Shot= week
Sick= waurepa
Sinew= wee-kau
Six= is-sto
Skin (human)= pos/poss
Skin/skins= teep
Skins (dressed)= rauhau
Sky= witta
Smoke= too-she
Snake= yau-hauk
Snow= wawawa
Soft= roosomme
Spear= waure
Spoon= cotsau
Squirrel= yehau
Star= wattapi untakeer
Step= pe
Stockings= rooesoo possoo
Sun= wittapare
Swan= atter
Swine= nommewarraupau
Ten= soone noponne
Theirs= -wa
There= mau
There are= -re
Three= nam mee
Tobacco= un-poone
Tobacco pipe= intom
Tobacco tongs= toc-koor
Tomorrow= kittape
Tree= yonne
Turd= pulawa
Turkey= yauta
Twelve= soone nomme
Twenty= winnop
Two= num-perre
Vein= wee-kau
Wampum= ettoco
Water= ejau
Weed= auk
White= waurraupa
Wife= yicauau
Wind= yuh
Wind blowing= yuh-hor
Wolf= tire kiro
Woman= yi
Woman (old)= yicau
Wood= yup
Yesterday= yottoha
Yours/Your= ya-/yi-
Will you go along with me?= Quake
All are drunk= nonnupper
I will sell you stuff cheap= nau hou hoore-ene
Got anything to eat?= noccoo eraute
"""


def normalize_woccon(w: str) -> str:
    return (w or "").strip().lower().replace(" ", "").replace("-", "").replace("'", "").replace("’", "")


def parse_source(s: str):
    """Yield (english, woccon) from lines like 'English= woccon'."""
    for line in s.strip().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        parts = line.split("=", 1)
        if len(parts) != 2:
            continue
        english = parts[0].strip()
        right = parts[1].strip()
        # Remove parenthetical pronunciation and citations, take first woccon token
        # e.g. "roosome (rue-sa-may)" -> "roosome"; "ejau (ay-jah-oo) -or- Ya- (yah)" -> "ejau"
        woccon = right
        for sep in [" (", " [", " -or-", "\t"]:
            if sep in woccon:
                woccon = woccon.split(sep)[0].strip()
        # Normalize spacing
        woccon = " ".join(woccon.split())
        if not english or not woccon:
            continue
        yield english, woccon


def main():
    staging_path = Path(__file__).resolve().parent.parent / "woccon_language" / "drive_staging" / "English-Woccon.json"
    with open(staging_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    staging_entries = data.get("lexicon_entries") or []
    staging_by_woccon = {}
    for e in staging_entries:
        w = (e.get("woccon") or "").strip()
        if w:
            key = normalize_woccon(w)
            if key not in staging_by_woccon:
                staging_by_woccon[key] = e
    staging_by_english = {}
    for e in staging_entries:
        eng = (e.get("english") or "").strip().lower()
        if eng:
            staging_by_english[eng] = e

    source_list = list(parse_source(SOURCE_ENTRIES))
    missing = []
    for english, woccon in source_list:
        key = normalize_woccon(woccon)
        eng_lower = english.lower()
        if key in staging_by_woccon:
            continue
        if eng_lower in staging_by_english:
            # same english might be different woccon (e.g. Turkey/Red both yauta)
            continue
        missing.append({"english": english, "woccon": woccon})

    print("English-Woccon source vs staging comparison")
    print("=" * 60)
    print(f"Source list entries (main vocabulary): {len(source_list)}")
    print(f"Staging lexicon_entries: {len(staging_entries)}")
    print(f"Missing from staging (source has but extraction did not produce): {len(missing)}")
    print()
    print("Missing entries (English = Woccon):")
    print("-" * 60)
    for m in missing:
        print(f"  {m['english']} = {m['woccon']}")

    out_path = Path(__file__).resolve().parent.parent / "woccon_language" / "drive_staging" / "English-Woccon-MISSING.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("Entries in the English-Woccon source doc that were NOT in the staging extraction.\n")
        f.write("(Water=ejau and 204 others)\n\n")
        for m in missing:
            f.write(f"{m['english']} = {m['woccon']}\n")
    print(f"\nWrote {out_path}")

    return missing


if __name__ == "__main__":
    main()
