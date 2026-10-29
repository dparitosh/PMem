package org.depo.reasoner;

import java.io.File;
import java.util.*;
import java.util.stream.Collectors;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.*;
import org.semanticweb.owlapi.profiles.*;
import org.semanticweb.owlapi.reasoner.*;
import org.semanticweb.owlapi.io.FileDocumentSource;
import org.semanticweb.HermiT.ReasonerFactory;

/** Offline, single-operation worker. Python supplies a verified import closure. */
public final class Main {
  public static void main(String[] args) throws Exception {
    // Independent wall-clock bound survives a forcibly terminated API parent.
    // The property is a CLI test seam; the API never supplies JVM properties.
    long maxMillis = Math.min(185000L,Math.max(10L,Long.getLong("depo.reasoner.maxMillis",185000L)));
    Thread watchdog = new Thread(() -> {
      try { Thread.sleep(maxMillis); Runtime.getRuntime().halt(124); }
      catch(InterruptedException stopped) { Thread.currentThread().interrupt(); }
    },"depo-reasoner-deadline");
    watchdog.setDaemon(true); watchdog.start();
    if(args.length != 2 && args.length != 3) throw new IllegalArgumentException("Expected input, result and optional target file");
    Map<String,Object> result = new LinkedHashMap<>();
    result.put("engine", "HermiT"); result.put("engine_version", "1.4.5.519");
    result.put("status", "unknown"); result.put("reasoner_executed", false);
    OWLReasoner reasoner = null;
    try {
      OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
      // OWLAPI's strict streaming parser rejects valid forward references in
      // Turtle restrictions. Validate the completed OWL2-DL profile instead;
      // never repair illegal punnings or accept unparsed input statements.
      OWLOntologyLoaderConfiguration config = new OWLOntologyLoaderConfiguration().setStrict(false)
          .setRepairIllegalPunnings(false).setConnectionTimeout(1).setRetriesToAttempt(0)
          .setMissingImportHandlingStrategy(MissingImportHandlingStrategy.THROW_EXCEPTION);
      OWLOntology ontology = manager.loadOntologyFromOntologyDocument(new FileDocumentSource(new File(args[0])),config);
      long unparsed = manager.getOntologyFormat(ontology).getOntologyLoaderMetaData().map(m -> m.getUnparsedTriples().count()).orElse(0L);
      result.put("parser_guessed_declaration_count",manager.getOntologyFormat(ontology).getOntologyLoaderMetaData().map(m -> m.getGuessedDeclarations().size()).orElse(0));
      if(unparsed > 0) {
        result.put("status","unsupported"); result.put("reason","unparsed_rdf_statements"); result.put("unparsed_statement_count",unparsed);
      } else if(!ontology.getImportsDeclarations().isEmpty()) {
        result.put("reason", "unresolved_imports");
      } else {
        OWLProfileReport profile = new OWL2DLProfile().checkOntology(ontology);
        result.put("owl2_dl_profile", profile.isInProfile());
        if(!profile.isInProfile()) {
          result.put("status", "unsupported");
          result.put("profile_violations", profile.getViolations().stream().limit(20).map(v -> v.getClass().getSimpleName()).collect(Collectors.toList()));
        } else {
          reasoner = new ReasonerFactory().createReasoner(ontology);
          result.put("reasoner_executed", true);
          boolean consistent = reasoner.isConsistent();
          result.put("status", consistent ? "consistent" : "inconsistent");
          if(consistent) {
            List<String> unsat = reasoner.getUnsatisfiableClasses().getEntitiesMinusBottom().stream().map(c -> c.getIRI().toString()).sorted().collect(Collectors.toList());
            result.put("unsatisfiable_class_count", unsat.size());
            result.put("unsatisfiable_classes", unsat.stream().limit(200).collect(Collectors.toList()));
            result.put("unsatisfiable_classes_complete", unsat.size() <= 200);
            if(args.length == 3) {
              String[] targets = new ObjectMapper().readValue(new File(args[2]), String[].class);
              if(targets.length > 32) throw new IllegalArgumentException("Too many selected targets");
              Map<String,String> checks = new LinkedHashMap<>();
              for(String target : targets) {
                if(target.length() > 512) throw new IllegalArgumentException("Target identity exceeds budget");
                IRI iri = IRI.create(target);
                checks.put(target, !ontology.containsClassInSignature(iri) ? "unknown" :
                    reasoner.isSatisfiable(manager.getOWLDataFactory().getOWLClass(iri)) ? "satisfiable" : "unsatisfiable");
              }
              result.put("target_checks", checks);
            }
            List<Map<String,String>> inferred = new ArrayList<>();
            List<OWLClass> classes = ontology.classesInSignature().sorted(Comparator.comparing(c -> c.getIRI().toString())).collect(Collectors.toList());
            outer: for(OWLClass cls: classes) {
              for(OWLClass parent: reasoner.getSuperClasses(cls, true).getFlattened().stream().sorted(Comparator.comparing(c -> c.getIRI().toString())).collect(Collectors.toList())) {
                if(parent.isOWLThing()) continue;
                inferred.add(Map.of("subject",cls.getIRI().toString(),"predicate","http://www.w3.org/2000/01/rdf-schema#subClassOf","object",parent.getIRI().toString()));
                if(inferred.size() >= 200) break outer;
              }
            }
            result.put("classification",inferred);
            result.put("classification_complete",classes.size() <= 200 && inferred.size() < 200);
          }
        }
      }
    } catch(Exception failure) {
      if(Boolean.getBoolean("depo.reasoner.debug")) failure.printStackTrace(System.err);
      result.put("status","unknown"); result.put("reason",failure.getClass().getSimpleName());
    } finally {
      if(reasoner != null) reasoner.dispose();
    }
    new ObjectMapper().writeValue(new File(args[1]),result);
  }
}
