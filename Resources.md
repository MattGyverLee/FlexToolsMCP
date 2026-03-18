Fieldworks A user-facing GUI tool for managing Lexicons (Calls C# liblcm Internally)
    ..\FieldWorks
    https://github.com/sillsdev/FieldWorks/
LibLCM: the internal data model an API governing all operations on a Fieldwords Database.
    ..\liblcm
    https://github.com/sillsdev/liblcm
FlexLibs (stable) A shallow and partial Ironpython wrapper that calls some liblcm functions to read and manipulate Flex Lexicons.
    ..\flexlibs
    https://github.com/cdfarrow/flexlibs/
FlexLibs 2.0 A deep and nearly-complete but untested Ironpython wrapper that wraps nearly all liblcm functions to read and manipulate Flex Lexicons.
    ..\flexlibs2
    https://github.com/mattgyverlee/flexlibs/
FLExTools: A Gui application for running prepared "macros" written in python. The python "macros" call FlexLibs if the function has been ported but must call liblcm directly in most cases.
    ..\flextools
    https://github.com/cdfarrow/flextools/

 So FLExtools is a linguist-friendly option used to run bulk changes on a Lexicon.

 1. FLExTools runs Ironpython scripts that call FlexLibs functions.
 2. FlexLibs functions are wrappers that call LibLCM (c# and object-oriented). LibLCM retrieves or changes the data in a lexicon.  The Fieldworks reads that database and shows the updated lexicon.
