<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:t="http://qifstandards.org/xsd/qif3">

  <!--
  Checks:
  * Excessively high-degree Surface (G-SU-HD)
  * Free edge (G-SH-FR)
  * Over-used edge (G-SH-NM)
  * Fragmented curve (G-CU-FG)
  
  New checks:
  * Unused parametric patches (G-SU-UN)
  * Unused mesh patches (G-SU-UN)
  * Inconsistent face on surface (G-FA-IT)
  * Multi-region parametric surface (G-FA-MU)
  * Multi-region mesh surface (G-FA-MU)
  * Over-used vertex (G-SH-OU)
  * Solid void (G-SO-VO)
  * Over-Used Face (G-FA-OU)
  * Unviewed Annotation (A-AN-UV)
  * Non-Graphical Annotation (A-AN-NG)
  * Multi-volume solid (G-SO-MU)
  * Inconsistent face in shell (G-SH-IT)
  -->

  <xsl:import href="CheckLibrary.xsl"/>
  
  <xsl:output method="xml" indent="yes" />
  
  <!-- skip text content -->
  <xsl:template match="text()" mode="Quality" />

  <!-- Excessively high-degree Surface (G-SU-HD) -->
  <xsl:template match="/t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceSet
                       /t:Nurbs23/t:Nurbs23Core"
		mode="Quality">
    <xsl:variable
	name="MaxDegree"
	select="$CheckParameters/CheckQualityParameters
		/Check[@name='G-SU-HD']/Parameter[@name='MaxDegree']"/>
    <xsl:if test="not(((t:OrderU - 1) &lt;= $MaxDegree) and 
		      ((t:OrderV - 1) &lt;= $MaxDegree))">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Excessively high-degree Surface (G-SU-HD):
	    id=<xsl:value-of select="../@id"/>,
	    ordU(<xsl:value-of select="t:OrderU"/>),
	    ordV(<xsl:value-of select="t:OrderV"/>),
	    MaxDegree(<xsl:value-of select="$MaxDegree"/>)
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <!-- Free edge (G-SH-FR) -->
  <xsl:template name="check_g_sh_fr">
    <xsl:param name="edge_id"/>
    <xsl:param name="n_link"/>
    <xsl:if test="$n_link = 1">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Free edge (G-SH-FR): id=<xsl:value-of select="$edge_id"/>,
            nEdgeRef(<xsl:value-of select="$n_link"/>)
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <!-- Over-used edge (G-SH-NM) -->
  <xsl:template name="check_g_sh_nm">
    <xsl:param name="edge_id"/>
    <xsl:param name="n_link"/>
    <xsl:if test="$n_link &gt; 2">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Over-used edge (G-SH-NM): id=<xsl:value-of select="$edge_id"/>,
            nEdgeRef(<xsl:value-of select="$n_link"/>)
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <!-- Fragmented curve (G-CU-FG) -->
  <xsl:template match="//t:Polyline13Core
                     | //t:Polyline12Core"
                mode="Quality">
    <xsl:variable
	name="MaxNumSegments"
	select="$CheckParameters/CheckQualityParameters
		/Check[@name='G-CU-FG']/Parameter[@name='MaxNumSegments']"/>
    <xsl:variable name="nSeg">
      <xsl:if test="t:Points">
        <xsl:value-of select="t:Points/@count"/>
      </xsl:if>
      <xsl:if test="t:PointsBinary">
        <xsl:value-of select="t:PointsBinary/@count"/>
      </xsl:if>
    </xsl:variable>
    <xsl:if test="not($nSeg &lt;= $MaxNumSegments)">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Fragmented curve (G-CU-FG): id=<xsl:value-of select="../@id"/>
	    nSeg(<xsl:value-of select="$nSeg"/>) greater than
	    MaxNumSegments(<xsl:value-of select="$MaxNumSegments"/>)
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <!-- Unused parametric patches (G-SU-UN) -->
  <xsl:template name="check_g_su_un_parametric">

    <xsl:variable name="surface_id">
      <xsl:value-of select="@id"/>
    </xsl:variable>

    <xsl:if test="not(/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:Face/t:Surface/t:Id[text()=$surface_id])">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Unused parametric patch (G-SU-UN):
            id=<xsl:value-of select="$surface_id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <!-- Unused mesh patches (G-SU-UN) -->
  <xsl:template name="check_g_su_un_mesh">

    <xsl:variable name="surface_id">
      <xsl:value-of select="@id"/>
    </xsl:variable>

    <xsl:if test="not(/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:FaceMesh/t:Mesh/t:Id[text()=$surface_id])">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Unused mesh patch (G-SU-UN):
            id=<xsl:value-of select="$surface_id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <!-- Inconsistent face on surface (G-FA-IT) -->
  <xsl:template name="check_g_fa_it">
    <xsl:if test="@turned = 'true' or @turned = 1">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Inconsistent face on surface (G-FA-IT):
            id=<xsl:value-of select="@id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <!-- Multi-region parametric surface (G-FA-MU) -->
  <xsl:template name="check_g_fa_mu_parametric">

    <xsl:variable name="surface_id">
      <xsl:value-of select="@id"/>
    </xsl:variable>

    <xsl:variable name="n_link">
      <xsl:value-of select="count(/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:Face/t:Surface/t:Id[text()=$surface_id])"/>
    </xsl:variable>

    <xsl:if test="$n_link &gt;= 2">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Multi-region parametric surface (G-FA-MU):
            id=<xsl:value-of select="$surface_id"/>,
            nLink=<xsl:value-of select="$n_link"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <!-- Multi-region mesh surface (G-FA-MU) -->
  <xsl:template name="check_g_fa_mu_mesh">

    <xsl:variable name="surface_id">
      <xsl:value-of select="@id"/>
    </xsl:variable>

    <xsl:variable name="n_link">
      <xsl:value-of select="count(/t:QIFDocument/t:Product/t:TopologySet/t:FaceMeshSet/t:FaceMesh/t:Mesh/t:Id[text()=$surface_id])"/>
    </xsl:variable>

    <xsl:if test="$n_link &gt;= 2">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Multi-region mesh surface (G-FA-MU):
            id=<xsl:value-of select="$surface_id"/>,
            nLink=<xsl:value-of select="$n_link"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <!-- Over-used vertex (G-SH-OU) -->
  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:VertexSet/t:Vertex"
		mode="Quality">

    <xsl:variable name="vertex_id">
      <xsl:value-of select="@id"/>
    </xsl:variable>

    <xsl:variable name="max_links">
      <xsl:value-of select="$CheckParameters/CheckQualityParameters/Check[@name='G-SH-OU']/Parameter[@name='MaxLinks']"/>
    </xsl:variable>
    
    <xsl:variable name="n_link">
      <xsl:value-of select="count(/t:QIFDocument/t:Product/t:TopologySet/t:EdgeSet/t:Edge/t:VertexBeg/t:Id[text()=$vertex_id]
                                | /t:QIFDocument/t:Product/t:TopologySet/t:EdgeSet/t:Edge/t:VertexEnd/t:Id[text()=$vertex_id])"/>
    </xsl:variable>

    <xsl:if test="$n_link &gt; $max_links">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Over-used vertex (G-SH-OU):
            id=<xsl:value-of select="$vertex_id"/>,
            nLink(<xsl:value-of select="$n_link"/>) greater than
            MaxLinks(<xsl:value-of select="$max_links"/>)
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <!-- Solid void (G-SO-VO) -->
  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:BodySet/t:Body/t:ShellIds"
		mode="Quality">

    <xsl:variable name="body_id">
      <xsl:value-of select="../@id"/>
    </xsl:variable>

    <xsl:variable name="n_shell">
      <xsl:value-of select="@n"/>
    </xsl:variable>

    <xsl:if test="$n_shell &gt; 1">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Solid void (G-SO-VO):
            id=<xsl:value-of select="$body_id"/>,
            nShell(<xsl:value-of select="$n_shell"/>) greater than 1
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <!-- Over-Used Face (G-FA-OU)  -->
  <xsl:template name="check_g_fa_ou">

    <xsl:variable name="face_id">
      <xsl:value-of select="@id"/>
    </xsl:variable>

    <xsl:variable name="n_link">
      <xsl:value-of select="count(/t:QIFDocument/t:Product/t:TopologySet/t:ShellSet/t:Shell/t:FaceIds/t:Id[text()=$face_id])"/>
    </xsl:variable>

    <xsl:if test="$n_link &gt; 1">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Over-Used Face (G-FA-OU):
            id=<xsl:value-of select="$face_id"/>,
            nLink(<xsl:value-of select="$n_link"/>) greater than 1
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <!-- Unviewed Annotation (A-AN-UV) -->
  <!-- Non-Graphical Annotation (A-AN-NG) -->
  <xsl:template match="/t:QIFDocument/t:Characteristics/t:CharacteristicNominals/t:*
             | /t:QIFDocument/t:Product/t:NoteSet/t:*
             | /t:QIFDocument/t:Product/t:NoteFlagSet/t:*
             | /t:QIFDocument/t:DatumDefinitions/t:*
             | /t:QIFDocument/t:DatumTargetDefinitions/t:*"
		mode="Quality">

    <xsl:variable name="ann_id">
      <xsl:value-of select="@id"/>
    </xsl:variable>

    <xsl:variable name="n_link_view">
      <xsl:value-of select="count(/t:QIFDocument/t:Product/t:ViewSet/t:SavedViewSet/t:SavedView/t:AnnotationVisibleIds/t:Id[text()=$ann_id]
                                | /t:QIFDocument/t:Product/t:ViewSet/t:SavedViewSet/t:SavedView/t:AnnotationHiddenIds/t:Id[text()=$ann_id])"/>
    </xsl:variable>

    <xsl:if test="$n_link_view = 0">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Unviewed Annotation (A-AN-UV):
            id=<xsl:value-of select="$ann_id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>

    <xsl:variable name="n_link_display">
      <xsl:value-of select="count(/t:QIFDocument/t:Product/t:VisualizationSet/t:PMIDisplaySet/t:PMIDisplay/t:Reference/t:Id[text()=$ann_id])"/>
    </xsl:variable>

    <xsl:if test="$n_link_display = 0">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Non-Graphical Annotation (A-AN-NG):
            id=<xsl:value-of select="$ann_id"/>
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>

    <xsl:apply-templates mode="Quality"/>
    
  </xsl:template>

  <!-- Multi-volume solid (G-SO-MU) -->
  <xsl:template match="/t:QIFDocument/t:Product/t:PartSet/t:Part
                     | /t:QIFDocument/t:Product/t:AssemblySet/t:Assembly"
		mode="Quality">

    <xsl:variable name="partasm_id">
      <xsl:value-of select="@id"/>
    </xsl:variable>

    <xsl:variable name="n_body">
      <xsl:value-of select="number(t:BodyIds/@n) + sum(t:FoldersPart/t:FolderPart/t:BodyIds/@n)"/>
    </xsl:variable>

    <xsl:if test="$n_body &gt; 1">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Multi-volume solid (G-SO-MU):
            id=<xsl:value-of select="$partasm_id"/>,
            nLink(<xsl:value-of select="$n_body"/>) greater than 1
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <!--
  Inconsistent face in shell (G-SH-IT), the check: face -> loop -> coedge -> edge <- coedge <- loop <- face
  not(turn1212 = sync2323) - error
  -->
  <xsl:template name="check_g_sh_it">
    <xsl:variable name="face_id" select="@id"/>
    <xsl:variable name="inconsistent_faces">
      <xsl:call-template name="find_inconsistent_face">
        <xsl:with-param name="face" select="."/>
      </xsl:call-template>
    </xsl:variable>
    <xsl:if test="not(string-length($inconsistent_faces) = 0)">
      <xsl:call-template name="error_node">
        <xsl:with-param name="report">
          Inconsistent face in shell (G-SH-IT):
          face=<xsl:value-of select="$face_id"/>,
          faces=<xsl:value-of select="normalize-space($inconsistent_faces)"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:if>
  </xsl:template>

  <xsl:template name="find_inconsistent_face">
    <xsl:param name="face"/>
    <xsl:variable name="face_id" select="$face/@id"/>
    <xsl:variable name="face_turned" select="$face/@turned = 'true' or $face/@turned = 1"/>
    <xsl:for-each select="$face/t:LoopIds/t:Id">
      <xsl:variable name="loop_id" select="text()"/>
      <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:Loop[@id = $loop_id]/t:CoEdges/t:CoEdge
                          | /t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:LoopMesh[@id = $loop_id]/t:CoEdgesMesh/t:CoEdgeMesh">
        <xsl:variable name="edge_id" select="t:EdgeOriented/t:Id/text()"/>
        <xsl:variable name="edge_index" select="position()"/>
        <xsl:variable name="edge_turned" select="t:EdgeOriented/@turned = 'true' or t:EdgeOriented/@turned = 1"/>
        <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:Face/t:LoopIds/t:Id
                            | /t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:FaceMesh/t:LoopIds/t:Id">
          <xsl:variable name="loop2_id" select="text()"/>
          <xsl:variable name="face2_id" select="../../@id"/>
          <xsl:variable name="face2_turned" select="../../@turned = 'true' or ../../@turned = 1"/>
          
          <xsl:if test="$face2_id != $face_id">
            <!-- co-edge in other face -->
            <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:Loop[@id = $loop2_id]/t:CoEdges/t:CoEdge/t:EdgeOriented/t:Id[text() = $edge_id]
                                | /t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:LoopMesh[@id = $loop2_id]/t:CoEdgesMesh/t:CoEdgeMesh/t:EdgeOriented/t:Id[text() = $edge_id]">
              <xsl:variable name="edge2_turned" select="../@turned = 'true' or ../@turned = 1"/>
              <xsl:variable name="turn1212" select="$edge_turned != $edge2_turned"/>
              <xsl:variable name="sync2323" select="$face_turned = $face2_turned"/>
              <xsl:if test="not($turn1212 = $sync2323)">
                <xsl:value-of select="$face2_id"/>,
              </xsl:if>
            </xsl:for-each>
          </xsl:if>

          <xsl:if test="$face2_id = $face_id">
            <!-- co-edge in the same face: skip origin edge_index, sync2323 always true -->
            <xsl:for-each select="/t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:Loop[@id=$loop2_id]/t:CoEdges/t:CoEdge[position() != $edge_index]/t:EdgeOriented/t:Id[text() = $edge_id]
                                | /t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:LoopMesh[@id=$loop2_id]/t:CoEdgesMesh/t:CoEdgeMesh[position() != $edge_index]/t:EdgeOriented/t:Id[text() = $edge_id]">
              <xsl:variable name="edge2_turned" select="../@turned = 'true' or ../@turned = 1"/>
              <xsl:variable name="turn1212" select="$edge_turned != $edge2_turned"/>
              <xsl:if test="not($turn1212)">
                <xsl:value-of select="$face2_id"/>,
              </xsl:if>
            </xsl:for-each>
          </xsl:if>
          
        </xsl:for-each>
      </xsl:for-each>
    </xsl:for-each>
  </xsl:template>
  
  <xsl:template match="/t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceSet/t:*" mode="Quality">
    <xsl:call-template name="check_g_su_un_parametric"/>
    <xsl:call-template name="check_g_fa_mu_parametric"/>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <xsl:template match="/t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceMeshSet/t:*" mode="Quality">
    <xsl:call-template name="check_g_su_un_mesh"/>
    <xsl:call-template name="check_g_fa_mu_mesh"/>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:Face" mode="Quality">
    <xsl:call-template name="check_g_fa_it"/>
    <xsl:call-template name="check_g_fa_ou"/>
    <xsl:call-template name="check_g_sh_it"/>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:FaceMesh" mode="Quality">
    <xsl:call-template name="check_g_fa_it"/>
    <xsl:call-template name="check_g_fa_ou"/>
    <xsl:call-template name="check_g_sh_it"/>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:FaceMesh" mode="Quality">
    <xsl:call-template name="check_g_fa_it"/>
    <xsl:call-template name="check_g_fa_ou"/>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

  <xsl:template match="/t:QIFDocument/t:Product/t:TopologySet/t:EdgeSet/t:Edge" mode="Quality">
    <xsl:variable name="edge_id" select="@id"/>
    <xsl:variable name="n_link" select="count(//t:QIFDocument/t:Product/t:TopologySet/t:LoopSet/t:Loop/t:CoEdges/t:CoEdge[t:EdgeOriented/t:Id = $edge_id])"/>
    <xsl:call-template name="check_g_sh_fr">
      <xsl:with-param name="edge_id" select="$edge_id"/>
      <xsl:with-param name="n_link" select="$n_link"/>
    </xsl:call-template>
    <xsl:call-template name="check_g_sh_nm">
      <xsl:with-param name="edge_id" select="$edge_id"/>
      <xsl:with-param name="n_link" select="$n_link"/>
    </xsl:call-template>
    <xsl:apply-templates mode="Quality"/>
  </xsl:template>

</xsl:stylesheet>
