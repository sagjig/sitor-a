# sitor-a
Using a sound-card, create SITOR-A/AMTOR ARQ/NBDP transmissions. This should be more-or-less able to make AMTOR transmissions as well. 
It cannot receive - I leave that function to the decoding software listed below, which is far more sophisticated in scope. This is just for satiating my urge to make SITOR-A modulation sounds, frankly.

Please note that this script was written almost entirely via LLM (namely, Google Gemini). It has been checked to a reasonable degree by myself, but this should be considered a "toy" project. None of the documentation in this README was written with an LLM.

⚠️ This is a hobbyist program. Please, please, _please_, don't use this for emergency or even just routine narrow-band direct-printing (NBDP) transmissions. This script, as it exists, is in no way to be considered reliable enough to be a proper, reliable, IMO-compliant implementation of NBDP communications standards. 

# Quick start
1. Install dependencies: `pip install numpy sounddevice`
2. `python3 sitor-a.py --tx "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG 1234567890?\!:().,'=//+" --no-ack --output 0`


# How to use:
1. Install Python 3 on your computer, as well as Git.
2. Using the terminal, install the depedencies using Python 3's pip tool: `pip install numpy sounddevice`
3. Clone this repo with Git. `git clone https://github.com/sagjig/sitor-a.git`
4. Enter the directory you just cloned with `cd sitor-a`.
5. Run program with `python3 sitor-a.py` For help, run `python3 sitor-a.py -h`.

For normal operation, you will need another station broadcasting a SITOR-A message relayed via your computer's sound card. This is inherent to the operation of SITOR-A, and is how it performs ARQ error correction.
For the uninitiated, ARQ (Automatic Repeat reQuest) essentially has the sender pause every few bytes, so the next station can either ACKnowledge receipt of those characters, or ask the sender to repeat those bytes. In SITOR-A, this is done every

If you just care about making the transmission/getting the sound of the transmission, run the program with the parameter `--no-ack`. This disables the ACK checking.

# Special thanks to:
- the Crypto Museum for the _excellent_ [breakdown of SITOR A and B](https://www.cryptomuseum.com/ref/sitor/#sitor_a).
- J. P. Martinez (G3PLX) for the [AMTOR article](https://www.arrl.org/files/file/History/History%20of%20QST%20Volume%201%20-%20Technology/QS06-81-Martinez.pdf).
- the engineers at Koninklijke TNT Post, for originally developing this wonderfully strange standard, and for the many years of reliable service it has provided to mariners across the world.

# Further reading
- [G4AON's article on AMTOR and TNCs](https://www.qsl.net/g4aon/amtor/), current as of May 2026. If you want a more reliable way of transmitting (and receiving) SITOR-A, you may want to pick up a PK232 Terminal Network Controller or anything else with an AMTOR hardware modem in it.
- [CLOVER-400](https://web.tapr.org/meetings/DCC_1996/DCC1996-WorldwideHFdataNetwork-WA8DRZ.pdf), a forward-compatible(?) data mode for HF maritime comms. 
- Alton J. Daley's [paper on HF radiotelex](https://ieeexplore.ieee.org/document/1622380/).
- Steve Watt (KD6GGD)'s [textfile](https://github.com/jbarke/textfiles.com/blob/12a04de3091d8d3fa1e5c98b96a2ab93e7b30006/textfiles.com/internet/FAQ/faqad1.txt#L297) on amateur packet radio.

# Recommended decoding software
The programs listed below are originally written for Windows, but I have tested these personally under Fedora Linux, using Wine.
- Sorcerer, by Avonlea Services, [hosted for download here by Dave M0TAZ](https://m0taz.co.uk/2016/03/sorcerer-decoding/). This program is older, but its SITOR decoding is superb. I have encountered very little errors and it seems to correctly acknowledge start and end of message segments.
- [TrueTTY by DXSoft](https://www.dxsoft.com/en/products/truetty/). The SITOR-ARQ decoding on this can be a little frazzled, but it works for the most part.
