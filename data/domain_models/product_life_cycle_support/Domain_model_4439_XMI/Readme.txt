ISO/TC 184/SC 4/WG 12 N11405

This zip file includes XMI and UMLDI files to be used to visualize the AP239 ed3 (PLCS) Application Domain Model in a SysML modeling tool.

NOTE 1 The completeness of the XMI file import process is dependant of the XMI implementation of the vendor software. These XMI files are canonical XMI files that are expected to be processed by canonical XMI tools before importing in a SysML modeling tool. 

To import the contents of this zip file in your SysML modeling tool use the following process: 

1) Set-up Ruby environment
- install Ruby, using for exampe ruby-install (https://www.ruby-lang.org/fr/documentation/installation/#ruby-install) or rubyInstaller for Windows (https://www.ruby-lang.org/fr/documentation/installation/#rubyinstaller)
- if not already installed, install required gems (using the "gem install xxx" command): 
	nokogiri (https://nokogiri.org/tutorials/installing_nokogiri.html)
	uuid
	rubyzip
Use the "gem list" command to list the intalled gems and check the above gems are installed.
If any issue, note that gems are available at https://rubygems.org/.

2) Install the Canonical XMI tool (https://sourceforge.net/projects/canonical-xmi-tools/) corresponding to your target SysML modeler, e.g. Papyrus, MagicDraw, UModel.

3) Unzip the XMI zip file. This creates a folder tree starting from the STEPlib folder.

4) For MagicDraw you need to set the STEPlib path variable to the newly created STEPlib folder. This is done by selecting the Options/Environment menu and "Path Variables", then use the Add button to add the STEPlib path variable and set its value.

5) Process the XMI files, in the following order:
                STEPlib/STEPlib.xmi 
                STEPlib/DataTypes.xmi 
                STEPlib/SysML_ARM/SysML_ARM.xmi 
                STEPlib/Core_model/Core_model.xmi 
This creates dvlp folders in the folders containing xmi files, with SysML files in them.

6) Process the Core_model folder, in Windows this is done by dragging and dropping the Core_model folder on to the gen**FromFolder batch file
NOTE 2 this will cycle through all XMI files in sub-folders of the selected folder so may take hours to process.

7) Process the AP239 XMI files, in the following order:
                STEPlib/Application_protocols/Application_protocols.xmi
                STEPlib/Application_protocols/AP239/AP239.xmi
                STEPlib/Application_protocols/AP239/Domain_model/Domain_model.xmi
