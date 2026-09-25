BLIND LABELLING — 41 cells of 50 m x 50 m, seed 7
Draw: Pallikaranai-West-1: 28, Pallikaranai-Control-Marsh: 7, Pallikaranai-Control-Builtup: 6

RULES (read before starting)
1. Do NOT open GeoGuard, its detections, or docs/evaluation.md while labelling.
2. For each cell open the Wayback link, then in the timeline on the left compare the
   release nearest 2020-12-16 with the one nearest 2023-06-13. The map opens
   centred on the cell; the cell is the 50 m square around the centre (about one or two
   house plots at zoom 19). Judge only what is inside that square.
3. Fill sheet.csv:
     label       one of:  new_built   (a structure, paved lot, compound wall or fill that was
                                        not there before and is still there after)
                          no_change   (same land cover both dates, incl. seasonal water/grass)
                          other_change (cleared / dug / burnt / flooded but no structure)
                          cannot_tell (cloud, missing tile, too ambiguous)
     confidence  1 (guess) – 3 (certain)
     note        free text, optional
4. Do all cells in one or two sittings; ~1 minute each.
5. When done, run:  python scripts\evaluate_blind.py  (see its header) — it scores every method
   against your labels and reports precision / recall with 95 % intervals.

CELLS
C001  12.93877, 80.19409
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.194088%2C12.938768%2C19
C002  12.94102, 80.19450
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.194503%2C12.941019%2C19
C003  12.94271, 80.19829
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.198288%2C12.942705%2C19
C004  12.94246, 80.19715
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.197146%2C12.942462%2C19
C005  12.93796, 80.19515
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.195150%2C12.937963%2C19
C006  12.94150, 80.19438
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.194382%2C12.941499%2C19
C007  12.93931, 80.19434
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.194343%2C12.939306%2C19
C008  12.93836, 80.19660
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.196601%2C12.938362%2C19
C009  12.94272, 80.19761
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.197611%2C12.942718%2C19
C010  12.94421, 80.18942
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.189417%2C12.944212%2C19
C011  12.93973, 80.19261
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.192614%2C12.939735%2C19
C012  12.94051, 80.19642
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.196416%2C12.940513%2C19
C013  12.93831, 80.19399
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.193992%2C12.938311%2C19
C014  12.94084, 80.19696
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.196958%2C12.940839%2C19
C015  12.94468, 80.18979
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.189791%2C12.944680%2C19
C016  12.94005, 80.19394
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.193936%2C12.940052%2C19
C017  12.94150, 80.19665
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.196648%2C12.941498%2C19
C018  12.94220, 80.19839
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.198392%2C12.942202%2C19
C019  12.94420, 80.18863
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.188634%2C12.944195%2C19
C020  12.93951, 80.19726
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.197257%2C12.939508%2C19
C021  12.94121, 80.19502
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.195023%2C12.941214%2C19
C022  12.94091, 80.19568
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.195684%2C12.940914%2C19
C023  12.93916, 80.19284
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.192840%2C12.939160%2C19
C024  12.93887, 80.19609
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.196086%2C12.938867%2C19
C025  12.94329, 80.19784
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.197840%2C12.943293%2C19
C026  12.94345, 80.18817
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.188170%2C12.943452%2C19
C027  12.93920, 80.19562
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.195617%2C12.939203%2C19
C028  12.94351, 80.18882
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.188824%2C12.943514%2C19
C029  12.93782, 80.19416
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.194157%2C12.937824%2C19
C030  12.94349, 80.18942
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.189419%2C12.943491%2C19
C031  12.93917, 80.19508
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.195085%2C12.939175%2C19
C032  12.93937, 80.19375
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.193754%2C12.939369%2C19
C033  12.94037, 80.19476
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.194762%2C12.940369%2C19
C034  12.93888, 80.19675
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.196752%2C12.938876%2C19
C035  12.94097, 80.19390
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.193904%2C12.940974%2C19
C036  12.94001, 80.19626
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.196263%2C12.940009%2C19
C037  12.94003, 80.19325
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.193247%2C12.940034%2C19
C038  12.94151, 80.19555
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.195550%2C12.941506%2C19
C039  12.94491, 80.18900
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.189000%2C12.944914%2C19
C040  12.93863, 80.19323
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.193228%2C12.938634%2C19
C041  12.94323, 80.19830
   https://livingatlas.arcgis.com/wayback/#active=all&mapCenter=80.198304%2C12.943234%2C19
