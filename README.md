# WenuyOS-uppdateringar – filgrenen

Den här grenen ersätts vid varje släpp (`packaging/filgren.sh` i New-wenuyos). Den innehåller de senaste
uppdateringarna, ett signerat index (`index.json.asc`) och programkatalogen. Datorerna hämtar med
`repo=https://raw.githubusercontent.com/danielwoxne/wenuyos-uppdateringar/filer/index.json.asc`.
Allt är signerat med WenuyOS-nyckeln – en ändrad fil installeras aldrig.
