<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:t="http://qifstandards.org/xsd/qif3">

  <!--
  Checks:
  * FeatureNominal, the check: must be connected to a topology entity
  * PositionCharacteristicDefinition, the check: if ToleranceValue = 0, then MaterialCondition must be MAXIMUM
  
  New checks:
  * Shell must refer to faces from the body that contains this shell. The check: body* -> shell -> faces (all from the same body)
  * Face must refer to loops from the body that contains this face. The check: body -> face -> loops (all from the same body)
  * Loop must refer to edges from the body that contains this loop. The check: body -> loops -> coedge -> edge (all from the same body)
  * Edge must refer to vertices from the body that contains this edge. The check: body -> edges -> vertex (all from the same body)
  * Faces from shell can be sewed with faces only from this shell. The check: shell -> face -> loop -> coedge -> edge <- coedge <- loop <- face <- shell2, shell != shell2 - error
  * Body form (SOLID, WIRE, TRIMMED_SURFACE)
  * Body - do not share topology with another bodies
  -->

  <xsl:import href="CheckLibrary.xsl"/>

  <xsl:output method="xml" indent="yes" />

  <!-- skip text content -->
  <xsl:template match="text()" mode="Semantic" />

  <!-- FeatureNominal, the check: must be connected to a topology entity -->
  <!-- This is currently not enabled in the CheckParameters and should  -->
  <!-- not be enabled because entities numbered by the nTopo variable  -->
  <!-- are not necessarily topology entities. Also, nTopo will always   -->
  <!-- be zero in 'select="$nTopo"', so it is pointless to evaluate it. -->
  <xsl:variable
      name="FeatureNominalTopologyLink"
      select="$CheckParameters/CheckSemanticParameters
	      /Check[@name='FeatureNominalTopologyLink']/@active = 'true'"/>
  <xsl:template match="/t:QIFDocument/t:Features/t:FeatureNominals/t:*"
		mode="Semantic">
    <xsl:if test="$FeatureNominalTopologyLink">
      <xsl:variable
	  name="nTopo"
	  select="count(t:EntityInternalIds/t:Id | t:EntityExternalIds/t:Id)"/>
      <xsl:if test="not($nTopo &gt; 0)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              FeatureNominal not connected with topology:
	      id=<xsl:value-of select="@id"/>, 
	      nTopo(<xsl:value-of select="$nTopo"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>
    <xsl:apply-templates mode="Semantic"/>
  </xsl:template>

  <!-- PositionCharacteristicDefinition, the check:                   -->
  <!-- if ToleranceValue = 0, then MaterialCondition must be MAXIMUM  -->
  <xsl:template
      match="/t:QIFDocument/t:Characteristics/t:CharacteristicDefinitions
	     /t:PositionCharacteristicDefinition" mode="Semantic">
    <xsl:if test="not((t:ToleranceValue != 0) or 
		      (t:MaterialCondition = 'MAXIMUM'))">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            PositionCharacteristicDefinition: 
	    id=<xsl:value-of select="@id"/>, ToleranceValue=0 and 
	    MaterialCondition(<xsl:value-of select="t:MaterialCondition"/>)
	    != 'MAXIMUM'
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
    <xsl:apply-templates mode="Semantic"/>
  </xsl:template>

  <!-- Shell must refer to faces from the body that contains this shell. The check: body* -> shell -> faces (all from the same body) -->
  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:ShellIds/t:Id" mode="Semantic">

    <xsl:variable name="shell_id">
      <xsl:value-of select="."/>
    </xsl:variable>

    <xsl:variable name="body_id">
      <xsl:value-of select="../../@id"/>
    </xsl:variable>

    <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:ShellSet/t:Shell[@id=$shell_id]/t:FaceIds/t:Id">
      <xsl:variable name="face_id">
        <xsl:value-of select="."/>
      </xsl:variable>
      <xsl:if test="not(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body[@id = $body_id]/t:FaceIds/t:Id[text()=$face_id])">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Shell refers to face from another body: body=<xsl:value-of select="$body_id"/>,
            shell=<xsl:value-of select="$shell_id"/>,
            face=<xsl:value-of select="$face_id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:if>
    </xsl:for-each>

    <xsl:apply-templates mode="Semantic"/>
  </xsl:template>

  <!-- Face must refer to loops from the body that contains this face. The check: body -> face -> loops (all from the same body) -->
  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:FaceIds/t:Id" mode="Semantic">
    <xsl:variable name="face_id" select="text()"/>
    <xsl:variable name="body_id" select="../../@id"/>
    <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:*[@id=$face_id]/t:LoopIds/t:Id">
      <xsl:variable name="loop_id" select="text()"/>
      <xsl:if test="not(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body[@id = $body_id]/t:LoopIds/t:Id[text()=$loop_id])">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Face refers to loop from another body: body=<xsl:value-of select="$body_id"/>,
            face=<xsl:value-of select="$face_id"/>,
            loop=<xsl:value-of select="$loop_id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:if>
    </xsl:for-each>
    <xsl:apply-templates mode="Semantic"/>
  </xsl:template>

  <!-- Loop must refer to edges from the body that contains this loop. The check: body -> loops -> coedge -> edge (all from the same body) -->
  <xsl:template
      match="/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:LoopIds/t:Id" mode="Semantic">

    <xsl:variable name="loop_id">
      <xsl:value-of select="."/>
    </xsl:variable>

    <xsl:variable name="body_id">
      <xsl:value-of select="../../@id"/>
    </xsl:variable>

    <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:Loop[@id=$loop_id]/t:CoEdges/t:CoEdge/t:EdgeOriented/t:Id
                        | /t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:LoopMesh[@id=$loop_id]/t:CoEdgesMesh/t:CoEdgeMesh/t:EdgeOriented/t:Id">
      <xsl:variable name="edge_id">
        <xsl:value-of select="."/>
      </xsl:variable>
      <xsl:if test="not(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body[@id = $body_id]/t:EdgeIds/t:Id[text()=$edge_id])">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Loop refers to edge from another body: body=<xsl:value-of select="$body_id"/>,
            loop=<xsl:value-of select="$loop_id"/>,
            edge=<xsl:value-of select="$edge_id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:if>
    </xsl:for-each>

    <xsl:apply-templates mode="Semantic"/>
  </xsl:template>

  <!-- Edge must refer to vertices from the body that contains this edge. The check: body -> edges -> vertex (all from the same body) -->
  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:EdgeIds/t:Id" mode="Semantic">

    <xsl:variable name="edge_id">
      <xsl:value-of select="."/>
    </xsl:variable>

    <xsl:variable name="body_id">
      <xsl:value-of select="../../@id"/>
    </xsl:variable>

    <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:EdgeSet/t:Edge[@id=$edge_id]/t:VertexBeg/t:Id
                        | /t:QIFDocument/t:Product/t:TopologySet/t:EdgeSet/t:Edge[@id=$edge_id]/t:VertexEnd/t:Id">
      <xsl:variable name="vertex_id">
        <xsl:value-of select="."/>
      </xsl:variable>
      <xsl:if test="not(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body[@id = $body_id]/t:VertexIds/t:Id[text()=$vertex_id])">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Edge refers to vertex from another body: body=<xsl:value-of select="$body_id"/>,
            edge=<xsl:value-of select="$edge_id"/>,
            vertex=<xsl:value-of select="$vertex_id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:if>
    </xsl:for-each>

    <xsl:apply-templates mode="Semantic"/>
  </xsl:template>

  <!--
  Faces from shell can be sewed with faces only from this shell. The check: shell -> face -> loop -> coedge -> edge <- coedge <- loop <- face <- shell2, shell != shell2 - error
  -->
  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:ShellSet/t:Shell/t:FaceIds/t:Id" mode="Semantic">
    
    <xsl:variable name="shell_id" select="../../@id"/>
    <xsl:variable name="face_id" select="."/>

    <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:Face[@id=$face_id]
                        | /t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:FaceMesh[@id=$face_id]">

      <xsl:variable name="find_other_shell_result">
        <xsl:call-template name="find_other_shell">
          <xsl:with-param name="face" select="."/>
          <xsl:with-param name="shell_id" select="$shell_id"/>
        </xsl:call-template>
      </xsl:variable>

      <xsl:if test="not(string-length($find_other_shell_result) = 0)">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Face from shell sewed with face from another shell: shell=<xsl:value-of select="$shell_id"/>,
            face=<xsl:value-of select="$face_id"/>
            <!--shells=<xsl:value-of select="normalize-space($find_other_shell_result)"/>-->
          </xsl:with-param>
        </xsl:call-template>
      </xsl:if>

    </xsl:for-each>
    
    <xsl:apply-templates mode="Semantic"/>
  </xsl:template>

  <xsl:template name="find_other_shell">
    <xsl:param name="face"/>
    <xsl:param name="shell_id"/>
    <xsl:for-each select="$face/t:LoopIds/t:Id">
      <xsl:variable name="loop_id" select="."/>
      <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:Loop[@id=$loop_id]/t:CoEdges/t:CoEdge/t:EdgeOriented/t:Id
                          | /t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:LoopMesh[@id=$loop_id]/t:CoEdgesMesh/t:CoEdgeMesh/t:EdgeOriented/t:Id">
        <xsl:variable name="edge_id" select="."/>
        <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:ShellSet/t:Shell[@id!=$shell_id]/t:FaceIds/t:Id">
          <xsl:variable name="face2_id" select="."/>
          <xsl:variable name="shell2_id" select="../../@id"/>
          <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:Face[@id=$face2_id]/t:LoopIds/t:Id
                              | /t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:FaceMesh[@id=$face2_id]/t:LoopIds/t:Id">
            <xsl:variable name="loop2_id" select="."/>
            <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:Loop[@id=$loop2_id]/t:CoEdges/t:CoEdge/t:EdgeOriented/t:Id[text()=$edge_id]
                                | /t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:LoopMesh[@id=$loop2_id]/t:CoEdgesMesh/t:CoEdgeMesh/t:EdgeOriented/t:Id[text()=$edge_id]">
              <xsl:value-of select="$shell2_id"/>,
            </xsl:for-each>
          </xsl:for-each>
        </xsl:for-each>
      </xsl:for-each>
    </xsl:for-each>
  </xsl:template>

  <!--
Body form, the check:
form = SOLID - has shells, has faces (TODO no open edges (slow))
form = WIRE - no shells, no faces
form = TRIMMED_SURFACE - has faces
-->

  <xsl:template name="check_body_form">

    <xsl:variable name="body_id" select="@id"/>
    <xsl:variable name="form" select="@form"/>
    <xsl:variable name="n_shell" select="count(t:ShellIds/t:Id)"/>
    <xsl:variable name="n_face" select="count(t:FaceIds/t:Id)"/>

    <xsl:if test="$form = 'WIRE' and not($n_shell = 0 and $n_face = 0)">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Body form: id(<xsl:value-of select="$body_id"/>),
            form(<xsl:value-of select="$form"/>),
            nShell(<xsl:value-of select="$n_shell"/>),
            nFace(<xsl:value-of select="$n_face"/>) - should not refer to faces and shells
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>

    <xsl:if test="$form = 'SOLID' and not($n_shell &gt; 0 and $n_face &gt; 0)">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Body form: id(<xsl:value-of select="$body_id"/>),
            form(<xsl:value-of select="$form"/>),
            nShell(<xsl:value-of select="$n_shell"/>),
            nFace(<xsl:value-of select="$n_face"/>) - should refer to faces and shells
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>

    <xsl:if test="$form = 'TRIMMED_SURFACE' and not($n_face &gt; 0)">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Body form: id(<xsl:value-of select="$body_id"/>),
            form(<xsl:value-of select="$form"/>),
            nShell(<xsl:value-of select="$n_shell"/>),
            nFace(<xsl:value-of select="$n_face"/>) - should refer to faces
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>

  </xsl:template>

  <!--
Body - do not share topology with another bodies
-->
  <xsl:template name="check_body_shared_topo">

    <xsl:variable name="body_id" select="@id"/>

    <!-- vertices -->
    <xsl:for-each select="t:VertexIds/t:Id">
      <xsl:variable name="vertex_id" select="text()"/>
      <xsl:variable name="n_link" select="count(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:VertexIds/t:Id[text() = $vertex_id])"/>
      <xsl:if test="not($n_link = 1)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              Body: id(<xsl:value-of select="$body_id"/>),
              vertex_id(<xsl:value-of select="$vertex_id"/>),
              n_link(<xsl:value-of select="$n_link"/>) - vertex shared between bodies
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:for-each>

    <!-- edges -->
    <xsl:for-each select="t:EdgeIds/t:Id">
      <xsl:variable name="edge_id" select="text()"/>
      <xsl:variable name="n_link" select="count(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:EdgeIds/t:Id[text() = $edge_id])"/>
      <xsl:if test="not($n_link = 1)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              Body: id(<xsl:value-of select="$body_id"/>),
              edge_id(<xsl:value-of select="$edge_id"/>),
              n_link(<xsl:value-of select="$n_link"/>) - edge shared between bodies
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:for-each>

    <!-- loops -->
    <xsl:for-each select="t:LoopIds/t:Id">
      <xsl:variable name="loop_id" select="text()"/>
      <xsl:variable name="n_link" select="count(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:LoopIds/t:Id[text() = $loop_id])"/>
      <xsl:if test="not($n_link = 1)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              Body: id(<xsl:value-of select="$body_id"/>),
              loop_id(<xsl:value-of select="$loop_id"/>),
              n_link(<xsl:value-of select="$n_link"/>) - loop shared between bodies
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:for-each>

    <!-- faces -->
    <xsl:for-each select="t:FaceIds/t:Id">
      <xsl:variable name="face_id" select="text()"/>
      <xsl:variable name="n_link" select="count(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:FaceIds/t:Id[text() = $face_id])"/>
      <xsl:if test="not($n_link = 1)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              Body: id(<xsl:value-of select="$body_id"/>),
              face_id(<xsl:value-of select="$face_id"/>),
              n_link(<xsl:value-of select="$n_link"/>) - face shared between bodies
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:for-each>

    <!-- shells -->
    <xsl:for-each select="t:ShellIds/t:Id">
      <xsl:variable name="shell_id" select="text()"/>
      <xsl:variable name="n_link" select="count(/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:ShellIds/t:Id[text() = $shell_id])"/>
      <xsl:if test="not($n_link = 1)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              Body: id(<xsl:value-of select="$body_id"/>),
              shell_id(<xsl:value-of select="$shell_id"/>),
              n_link(<xsl:value-of select="$n_link"/>) - shell shared between bodies
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:for-each>

  </xsl:template>

  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body"
              mode="Semantic">
    <xsl:call-template name="check_body_shared_topo"/>
    <xsl:call-template name="check_body_form"/>
    <xsl:apply-templates mode="Semantic"/>
  </xsl:template>
  
</xsl:stylesheet>
