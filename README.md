<p align="center"><img width="50%" alt="TuyaGateway logo" src="https://raw.githubusercontent.com/wiki/TradeFace/tuyagateway/img/tuyagateway_logo.png"></p>

We've made a library that communicates locally with your Tuya devices (no internet connection needed), called [TuyaFace](https://github.com/TradeFace/tuyaface). The library is open-source and can be used in your own software if you choose to do so. But we did the heavylifting already for you. TuyaGateway implements the library and communitates over an open protocol (MQTT) with your home automation software. All relevant home automation software packages (e.g. Home Assistant) are able to work with MQTT. 

Great! But what about GismoCaster? [GismoCaster](https://github.com/TradeFace/gismocaster) is the control-center for TuyaGateway. In a webinterface you can add your devices, set names for them, etc. So, no programming required and no dabbling around in obscure text files which will break when you add a tab to many.

<p align="center"><img alt="Network" src="https://raw.githubusercontent.com/wiki/TradeFace/tuyagateway/img/network_bg.png"></p>

A bit more technical
----------
TuyaGateway listens on MQTT topics and routes requests to your Tuya devices. In earlier versions the configuration was based on a one to one topic translation in e.g. Home-Assistant config-files. 1:1 topic translation is limited to simple tasks (like switching ON/OFF); only boolean values. 

From v1.1 onwards Tuya device configuration can be done with [GismoCaster](https://github.com/TradeFace/gismocaster). In which you can set discovery messages for both TuyaGateway and Home Assistant and opens up the ability to set boolean/integer/float/string types. 

The goal for version v2.0 is to add input/output processing functions and to improve on HA message values. Next to structural improvements to the code. The topic configuration option will be removed.


[Docs](https://github.com/TradeFace/tuyagateway/wiki)
================
https://github.com/TradeFace/tuyagateway/wiki

Get involved!
================
Anyone who is willing to test, write code, add documentation, etc. is welcome to make a [contribution](https://github.com/TradeFace/tuyagateway/blob/development/CONTRIBUTING.md). 


Acknowledgements
=================
- https://github.com/emontnemery development tuyaclient and implementation in tuyagateway
- https://github.com/jkerdreux-imt testing tuyaclient
- https://github.com/SDNick484 testing protocol 3.1 reimplementation
