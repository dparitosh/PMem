# Reasoner dependencies

DEPO's worker calls HermiT 1.4.5.519 through OWLAPI. It does not use Owlready2.
HermiT: https://github.com/owlcs/hermit-reasoner (LGPL; preserve upstream notices).
OWLAPI: https://github.com/owlcs/owlapi (upstream dual LGPL/Apache licensing).
Jackson: https://github.com/FasterXML/jackson-databind (Apache 2.0).

The Maven POM and worker Java source are shipped for rebuilding/replacing the
reasoner artifact. Maven preserves dependency license/notice resources in the JAR;
distribution must retain applicable upstream notices and license obligations.
IDO has its separate CC BY-SA attribution under resources/foundation/NOTICE.md.
Do not describe these components or the derived DEPO business module as an
ISO-certified implementation. Customer release review includes dependency and
license review of the resolved Maven dependency tree, not just this summary.
