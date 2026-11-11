<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:t="http://qifstandards.org/xsd/qif3"
                xmlns:user="urn:my-scripts"
                >

  <!--
  Checks:
  * idMax
  * Links with external documents
  * 2D/3D NURBS curves, the check: the number of control points = the number of knots - the curve order
  * NURBS surface, the check: the number of control points = ('nKtU' - 'ordU')*('nKtV' - 'ordV')
  * Array of elements, the check: number of elements must be equal to a value specified in the attribute 'n'
  * Unit vector (3d)
  
  New checks:
  * 2D/3D NURBS curves and NURBS surface, the check: the number of control points = the number of weight coefficients
  * MeshTriangleCore, the checks: the number of neighbours = the number of triangles, the number of normals = the number of vertices
  * (MSXML) ArrayDoubleType, the check: number of doubles = @count
  * (MSXML) ArrayPoint2dType, the check: number of doubles = @count * 2
  * (MSXML) ArrayPointType, the check: number of doubles = @count * 3
  * (MSXML) ArrayI2Type, the check: number of integers = @count * 2
  * FaceMesh, the checks: nTrVisible <= nTr, nTrHidden <= nTr, nTrColor = nTr

  To disable MSXML extensions:
  1) comment import checkLibraryMSXML.xsl
  2) use_msxml = false()
  
  To use MSXML extensions on Windows platform, use .net library, register runtime extensions not required
  1) uncomment import checkLibraryMSXML.xsl
  2) use_msxml = true()

  To use MSXML extensions on Windows/Linux/MacOS platform, use .net core library, register runtime extensions
  1) comment import checkLibraryMSXML.xsl
  2) use_msxml = true()
  3) register extension functions from checkLibraryMSXML.xsl by XsltArgumentList.AddExtensionObject("urn:my-scripts", extension_object);
  -->
  
  <xsl:import href="CheckLibrary.xsl"/>
  <!--<xsl:import href="CheckLibraryMSXML.xsl"/>-->
  <xsl:output method="xml" indent="yes" />
  <xsl:variable name="use_msxml" select="true()"/>

  <!-- skip text content -->
  <xsl:template match="text()" mode="Format" />

  <!-- idMax -->
  <xsl:template match="//t:*[@id &gt; /t:QIFDocument/@idMax]" mode="Format">
    <xsl:call-template name="error_node">
      <xsl:with-param name="report">
        The id of element is greater than idMax.
	id(<xsl:value-of select="@id"/>) greater than
	idMax(<xsl:value-of select="/t:QIFDocument/@idMax"/>).
      </xsl:with-param>
    </xsl:call-template>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

  <!-- Links with external documents -->
  <!-- Warning: some XSLT 1.0 processors (e.g. the one in XMLSpy) signal -->
  <!-- an error if the document function does not find what it is        -->
  <!-- looking for and no output file is produced. Other XSLT processors -->
  <!-- (e.g. xsltproc) return an empty node list that can be tested,     -->
  <!-- and will produce an output file if the document function fails.   -->

  <xsl:template
    match="t:ExternalQIFReferences/t:ExternalQIFDocument"
    mode="Format">
    <xsl:variable name="id" select="@id"/>
    <xsl:variable name="QPId" select="t:QPId"/>
    <xsl:variable name="URI" select="t:URI"/>
    <xsl:choose>
      <xsl:when test="document($URI)">
	<xsl:variable name="docExt" select="document($URI)/t:QIFDocument"/>
	<xsl:variable name="QPIdExt" select="$docExt/t:QPId"/>
	<xsl:choose>
	  <xsl:when test="not($QPId = $QPIdExt)">
            <xsl:call-template name="error_node">
              <xsl:with-param name="report">
		The external document has a different QPId.
		URI = <xsl:value-of select="$URI"/>,
		QPId(<xsl:value-of select="$QPId"/>)
		!= QPIdExt(<xsl:value-of select="$QPIdExt"/>).
              </xsl:with-param>
            </xsl:call-template>
	  </xsl:when>
	  <xsl:otherwise>
            <xsl:for-each select="//t:*[@xId][. = $id]">
              <xsl:variable name="xId" select="@xId"/>
              <xsl:if test="not(count($docExt//t:*[@id = $xId]) = 1)">
		<xsl:call-template name="error_node">
		  <xsl:with-param name="report">
                    The external entity with this id was not found.
		    URI = <xsl:value-of select="$URI"/>,
		    idDoc(<xsl:value-of select="$id"/>),
		    xId(<xsl:value-of select="$xId"/>).
		  </xsl:with-param>
		</xsl:call-template>
              </xsl:if>
            </xsl:for-each>
	  </xsl:otherwise>
	</xsl:choose>
      </xsl:when>
      <xsl:otherwise>
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
	    The external document was not found
	    URI = <xsl:value-of select="$URI"/>.
          </xsl:with-param>
        </xsl:call-template>
      </xsl:otherwise>
    </xsl:choose>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

  <!--

2D/3D NURBS curves, the check: the number of control points = the number of
knots - the curve order

-->

  <xsl:template name="check_nurbs1x_ncp_nkt_nwt">

    <xsl:variable name="nCP">
      <xsl:if test="t:CPs">
        <xsl:value-of select="t:CPs/@count"/>
      </xsl:if>
      <xsl:if test="t:CPsBinary">
        <xsl:value-of select="t:CPsBinary/@count"/>
      </xsl:if>
    </xsl:variable>

    <xsl:if test="not($nCP = t:Knots/@count - t:Order)">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Nurbs12Core/Nurbs13Core: id=<xsl:value-of select="../@id"/>,
	    nCP(<xsl:value-of select="$nCP"/>)
	    != nKt(<xsl:value-of select="t:Knots/@count"/>) - 
	    order(<xsl:value-of select="t:Order"/>)
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

<!-- NURBS surface, the check:
   the number of control points = ('nKtU' - 'ordU')*('nKtV' - 'ordV') -->

  <xsl:template name="check_nurbs23_ncp_nkt_nwt">

    <xsl:variable name="nCP">
      <xsl:if test="t:CPs">
        <xsl:value-of select="t:CPs/@count"/>
      </xsl:if>
      <xsl:if test="t:CPsBinary">
        <xsl:value-of select="t:CPsBinary/@count"/>
      </xsl:if>
    </xsl:variable>
    <xsl:if test="not($nCP = (t:KnotsU/@count - t:OrderU) *
		             (t:KnotsV/@count - t:OrderV))">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Nurbs23Core: id=<xsl:value-of select="../@id"/>,
            nCP(<xsl:value-of select="$nCP"/>) !=
            (nKtU(<xsl:value-of select="t:KnotsU/@count"/>) -
            ordU(<xsl:value-of select="t:OrderU"/>)) *
            (nKtV(<xsl:value-of select="t:KnotsV/@count"/>) -
            ordV(<xsl:value-of select="t:OrderV"/>))
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>
  
  <!-- Array of elements, the check: number of elements must be equal to
       a value specified in the attribute 'n' -->

  <xsl:template match="//t:*[@n]" mode="Format">
    <xsl:if test="not(@n = count(t:*))">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            The number of array elements doesn't correspond to the
	    specified "n" attribute: n(<xsl:value-of select="@n"/>) != 
	    nElem(<xsl:value-of select="count(t:*)"/>)
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

<!--

template for the square of the length of a 3D vector represented as an
xs:list of three numerical values.

-->

  <xsl:template name="lengthSquare3D">
    <xsl:param name="vec3D"/>
    <xsl:variable name="norm">
      <xsl:value-of select="normalize-space($vec3D)"/>
    </xsl:variable>
    <xsl:variable name="first">
      <xsl:value-of select='substring-before($norm, " ")'/>
    </xsl:variable>
    <xsl:variable name="rest">
      <xsl:value-of select='substring-after($norm, " ")'/>
    </xsl:variable>
    <xsl:variable name="second">
      <xsl:value-of select='substring-before($rest, " ")'/>
    </xsl:variable>
    <xsl:variable name="third">
      <xsl:value-of select='substring-after($rest, " ")'/>
    </xsl:variable>
    <xsl:variable name="x">
      <xsl:value-of select="number($first)"/>
    </xsl:variable>
    <xsl:variable name="y">
      <xsl:value-of select="number($second)"/>
    </xsl:variable>
    <xsl:variable name="z">
      <xsl:value-of select="number($third)"/>
    </xsl:variable>
    <xsl:value-of select="($x*$x) + ($y*$y) + ($z*$z)"/>
  </xsl:template>

<!--

Unit vector, the check: the sum of the squares of the components must
not be less than MinLength squared and must not be greater than MaxLength
squared. MinLength and MaxLength are parameters from CheckParameters.xml.

This is checking only 3D unit vectors. 

See the file unitVectors.txt for an analysis of where all elements are
found whose type is a 3D unit vector type; there are four 3D unit vector
types.
-->

 <xsl:template
     match="//t:AnalysisVector
          | //t:AxisDirection
          | //t:AxisVector
          | //t:DatumTargetTranslationDirection
          | //t:DepthVector
          | //t:DirMeridianPrime
          | //t:DirNorthPole
          | //t:LengthDirection
          | //t:LengthVector
          | //t:NominalDirection
          | //t:Normal
          | //t:NormalSpecial
          | //t:OriginDirection
          | //t:PrimaryAxis
          | //t:RectangularUnitAreaOrientation
          | //t:RotationAxis
          | //t:SecondaryAxis
          | //t:Vector
          | //t:WidthDirection
          | //t:XDirection
          | //t:YDirection
          | //t:ZDirection
          | //t:ZoneDirection
          | //t:ZoneOrientationVector
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:AdjacentNormal 
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:Direction
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:DraftVector
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:FeatureDirection
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:LineDirection
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:PlaneNormal
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:StartDirection
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:Axis/t:Direction
          | /t:QIFDocument/t:Features/t:FeatureNominals/t:*/t:Sweep/t:DirBeg
          | /t:QIFDocument/t:FeatureZones/t:FeatureZoneAreaCylindrical
            /t:Cylinder/t:Axis
          | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve13Set
            /t:ArcCircular13/t:ArcCircular13Core/t:DirBeg
          | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve13Set
            /t:ArcConic13/t:ArcConic13Core/t:DirBeg
          | /t:QIFDocument/t:Product/t:VisualizationSet/t:PMIDisplaySet
            /t:PMIDisplay/t:Plane/t:Direction
          | /t:QIFDocument/t:Product/t:ViewSet/t:AnnotationViewSet
            /t:AnnotationView/t:Direction
          | /t:QIFDocument/t:Product/t:ViewSet/t:ExplodedViewSet
            /t:ExplodedView/t:MoveGroups/t:MoveGroup/t:Translate/t:Direction
          | /t:QIFDocument/t:Product/t:ViewSet/t:ExplodedViewSet
            /t:ExplodedView/t:MoveGroups/t:MoveGroup/t:Rotate/t:Axis
          | /t:QIFDocument/t:Product/t:ZoneSectionSet/t:ZoneSection
            /t:SectionPlanes/t:SectionPlane/t:Plane/t:Direction
          | /t:QIFDocument/t:MeasurementsResults/t:MeasurementResultsSet
            /t:MeasurementResults/t:MeasuredFeatures/t:*
            /t:SweepFull/t:DirBeg
          | /t:QIFDocument/t:MeasurementsResults/t:MeasurementResultsSet
            /t:MeasurementResults/t:MeasuredFeatures/t:*
            /t:SweepMeasurementRange/t:DirBeg
          | /t:QIFDocument/t:MeasurementsResults/t:MeasurementResultsSet/
             t:MeasurementResults/t:MeasuredFeatures/t:*/t:Axis/t:Direction"
     mode="Format">
    <xsl:variable
      name="minLength"
      select="$CheckParameters/CheckFormatParameters
             /Check[@name='unitVectorLength']/Parameter[@name='MinLength']"/>
    <xsl:variable
      name="maxLength"
      select="$CheckParameters/CheckFormatParameters
             /Check[@name='unitVectorLength']/Parameter[@name='MaxLength']"/>
    <xsl:variable name="minSquare" select="$minLength*$minLength"/>
    <xsl:variable name="maxSquare" select="$maxLength*$maxLength"/>
    <xsl:variable name="lengthSquare">
      <xsl:call-template name="lengthSquare3D">
        <xsl:with-param name="vec3D" select="." />
      </xsl:call-template>
    </xsl:variable>
    <xsl:if test="$lengthSquare &gt; $maxSquare">
      <xsl:call-template name="error_node">
        <xsl:with-param name="report">
          Unit vector too long: length of (<xsl:value-of select="."/>)
	  greater than <xsl:value-of select="$maxLength"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:if>
    <xsl:if test="$lengthSquare &lt; $minSquare">
      <xsl:call-template name="error_node">
        <xsl:with-param name="report">
          Unit vector too short: length of (<xsl:value-of select="."/>)
          less than <xsl:value-of select="$minLength"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:if>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

  <!--
2D/3D NURBS curves and NURBS surface, the check: the number of control points =
the number of weight coefficients
-->

  <xsl:template name="check_nurbs_ncp_nwt">

    <xsl:if test="t:Weights">
      <xsl:variable name="nCP">
        <xsl:if test="t:CPs">
          <xsl:value-of select="t:CPs/@count"/>
        </xsl:if>
        <xsl:if test="t:CPsBinary">
          <xsl:value-of select="t:CPsBinary/@count"/>
        </xsl:if>
      </xsl:variable>
      <xsl:variable name="nWt">
        <xsl:value-of select="t:Weights/@count"/>
      </xsl:variable>
      <xsl:if test="not($nCP = $nWt)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              Nurbs12Core/Nurbs13Core/Nurbs23Core: id=<xsl:value-of select="../@id"/>,
              nCP(<xsl:value-of select="$nCP"/>)
              != nWt(<xsl:value-of select="$nWt"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>

  </xsl:template>

<!--
MeshTriangleCore, the checks:
the number of neighbours = the number of triangles,
the number of normals = the number of vertices
-->

  <xsl:template
    match="/t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceMeshSet/t:MeshTriangle
           /t:MeshTriangleCore"
                mode="Format">

    <!-- nNb = nTr? -->
    <xsl:if test="t:Neighbours|t:NeighboursBinary">
      <xsl:variable name="nNb">
        <xsl:if test="t:Neighbours">
          <xsl:value-of select="t:Neighbours/@count"/>
        </xsl:if>
        <xsl:if test="t:NeighboursBinary">
          <xsl:value-of select="t:NeighboursBinary/@count"/>
        </xsl:if>
      </xsl:variable>
      
      <xsl:variable name="nTr">
        <xsl:if test="t:Triangles">
          <xsl:value-of select="t:Triangles/@count"/>
        </xsl:if>
        <xsl:if test="t:TrianglesBinary">
          <xsl:value-of select="t:TrianglesBinary/@count"/>
        </xsl:if>
      </xsl:variable>
      
      <xsl:if test="not($nNb = $nTr)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              MeshTriangleCore: id=<xsl:value-of select="../@id"/>,
              nNb(<xsl:value-of select="$nNb"/>)
              != nTr(<xsl:value-of select="$nTr"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>

    <!-- nNm = nVx? -->
    <xsl:if test="t:Normals|t:NormalsBinary">
      <xsl:variable name="nNm">
        <xsl:if test="t:Normals">
          <xsl:value-of select="t:Normals/@count"/>
        </xsl:if>
        <xsl:if test="t:NormalsBinary">
          <xsl:value-of select="t:NormalsBinary/@count"/>
        </xsl:if>
      </xsl:variable>
      
      <xsl:variable name="nVx">
        <xsl:if test="t:Vertices">
          <xsl:value-of select="t:Vertices/@count"/>
        </xsl:if>
        <xsl:if test="t:VerticesBinary">
          <xsl:value-of select="t:VerticesBinary/@count"/>
        </xsl:if>
      </xsl:variable>
      
      <xsl:if test="not($nNm = $nVx)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              MeshTriangleCore: id=<xsl:value-of select="../@id"/>,
              nNm(<xsl:value-of select="$nNm"/>)
              != nVx(<xsl:value-of select="$nVx"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>

    <xsl:apply-templates mode="Format"/>

  </xsl:template>

<!--
ArrayDoubleType, the check: number of doubles = @count
-->
  
  <xsl:template
  match="/t:QIFDocument/t:Product/t:GeometrySet/t:Curve12Set/t:Nurbs12/t:Nurbs12Core/t:Knots
       | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve12Set/t:Nurbs12/t:Nurbs12Core/t:Weights
       | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve13Set/t:Nurbs13/t:Nurbs13Core/t:Knots
       | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve13Set/t:Nurbs13/t:Nurbs13Core/t:Weights
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceSet/t:Nurbs23/t:Nurbs23Core/t:KnotsU
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceSet/t:Nurbs23/t:Nurbs23Core/t:KnotsV
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceSet/t:Nurbs23/t:Nurbs23Core/t:Weights
  "
              mode="Format">
    <xsl:if test="$use_msxml">
      <xsl:variable name="nNumberActual" select="user:LengthArrayDouble(.)"/>
      <xsl:variable name="count" select="@count"/>
      <xsl:if test="not($nNumberActual = $count)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              ArrayDoubleType: nNumberActual(<xsl:value-of select="$nNumberActual"/>)
              != count(<xsl:value-of select="$count"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

<!--
ArrayPoint2dType, the check: number of doubles = @count * 2
-->

  <xsl:template
  match="/t:QIFDocument/t:Product/t:GeometrySet/t:Curve12Set/t:Nurbs12/t:Nurbs12Core/t:CPs
  "
              mode="Format">
    <xsl:if test="$use_msxml">
      <xsl:variable name="count" select="@count"/>
      <xsl:variable name="nNumberActual" select="user:LengthArrayDouble(.)"/>
      <xsl:variable name="nNumberRequired" select="$count * 2"/>
      <xsl:if test="not($nNumberActual = $nNumberRequired)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              ArrayPoint2dType: nNumberActual(<xsl:value-of select="$nNumberActual"/>)
              != nNumberRequired(<xsl:value-of select="$nNumberRequired"/>),
              count(<xsl:value-of select="$count"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

  <!--
ArrayPointType, the check: number of doubles = @count * 3
-->

  <xsl:template
  match="/t:QIFDocument/t:Product/t:GeometrySet/t:Curve13Set/t:Nurbs13/t:Nurbs13Core/t:CPs
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceSet/t:Nurbs23/t:Nurbs23Core/t:CPs
  "
              mode="Format">
    <xsl:if test="$use_msxml">
      <xsl:variable name="count" select="@count"/>
      <xsl:variable name="nNumberActual" select="user:LengthArrayDouble(.)"/>
      <xsl:variable name="nNumberRequired" select="$count * 3"/>
      <xsl:if test="not($nNumberActual = $nNumberRequired)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              ArrayPointType: nNumberActual(<xsl:value-of select="$nNumberActual"/>)
              != nNumberRequired(<xsl:value-of select="$nNumberRequired"/>),
              count(<xsl:value-of select="$count"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

  <!--
ArrayI2Type, the check: number of integers = @count * 2
-->

  <xsl:template
  match="/t:QIFDocument/t:Product/t:GeometrySet/t:CurveMeshSet/t:PathTriangulation/t:PathTriangulationCore/t:Edges
  "
              mode="Format">
    <xsl:if test="$use_msxml">
      <xsl:variable name="count" select="@count"/>
      <xsl:variable name="nNumberActual" select="user:LengthArrayInt(.)"/>
      <xsl:variable name="nNumberRequired" select="$count * 2"/>
      <xsl:if test="not($nNumberActual = $nNumberRequired)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              ArrayI2Type: nNumberActual(<xsl:value-of select="$nNumberActual"/>)
              != nNumberRequired(<xsl:value-of select="$nNumberRequired"/>),
              count(<xsl:value-of select="$count"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

  <!--
Base64 size, the check: number of integers = @count * 2
-->

  <!--<xsl:template
  match="/t:QIFDocument/t:Product/t:GeometrySet/t:Curve13Set/t:Polyline13/t:Polyline13Core/t:PointsBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve12Set/t:Polyline12/t:Polyline12Core/t:PointsBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve13Set/t:Nurbs13/t:Nurbs13Core/t:CPsBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve12Set/t:Nurbs12/t:Nurbs12Core/t:CPsBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceSet/t:Nurbs23/t:Nurbs23Core/t:CPsBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceMeshSet/t:MeshTriangle/t:NormalsSpecialBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceMeshSet/t:MeshTriangle/t:MeshTriangleCore/t:TrianglesBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceMeshSet/t:MeshTriangle/t:MeshTriangleCore/t:NeighboursBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceMeshSet/t:MeshTriangle/t:MeshTriangleCore/t:VerticesBinary
       | /t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceMeshSet/t:MeshTriangle/t:MeshTriangleCore/t:NormalsBinary
  "
              mode="Format">

    <xsl:variable name="base64_str">
      <xsl:value-of select="translate(text(), ' &#09;&#10;&#13;', '')"/>
    </xsl:variable>

    <xsl:variable name="base64_str_len_actual">
      <xsl:value-of select="string-length($base64_str)"/>
    </xsl:variable>

    <xsl:variable name="base64_data_len_required">
      <xsl:value-of select="number(@count) * number(@sizeElement)"/>
    </xsl:variable>
    
    <xsl:variable name="base64_str_len_required">
      <xsl:value-of select="4*floor((number($base64_data_len_required) + 2) div 3)"/>
    </xsl:variable>

    --><!--<len len_base64="{$len_base64}" len_calc="{$len_calc}"/>--><!--

    <xsl:if test="not($base64_str_len_actual = $base64_str_len_required)">
      <xsl:for-each select=".">
        <xsl:call-template name="error_node">
          <xsl:with-param name="report">
            Base64 data length: actual(<xsl:value-of select="$base64_str_len_actual"/>)
            != required(<xsl:value-of select="$base64_str_len_required"/>)
          </xsl:with-param>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>

    <xsl:apply-templates mode="Format"/>

  </xsl:template>-->

<!--
FaceMesh, the checks:
the number of visible triangles <= the number of triangles,
the number of hidden triangles <= the number of triangles,
the number of triangle colors = the number of triangles
-->

  <xsl:template
    match="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:FaceMesh"
                mode="Format">

    <!--facemesh_1 = <xsl:value-of select="@id"/>-->
    
    <xsl:variable name="face_id" select="@id"/>

    <xsl:variable name="nTr">
      <xsl:call-template name="meshtriangle_n_tr">
        <xsl:with-param name="mesh_id" select="t:Mesh/t:Id/text()"/>
      </xsl:call-template>
    </xsl:variable>

    <!-- nTrVisible <= nTr -->
    <xsl:if test="t:TrianglesVisible|t:TrianglesVisibleBinary">
      
      <xsl:variable name="nTrVisible">
        <xsl:if test="t:TrianglesVisible">
          <xsl:value-of select="t:TrianglesVisible/@count"/>
        </xsl:if>
        <xsl:if test="t:TrianglesVisibleBinary">
          <xsl:value-of select="t:TrianglesVisibleBinary/@count"/>
        </xsl:if>
      </xsl:variable>

      <xsl:if test="not($nTrVisible &lt;= $nTr)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              FaceMesh: id=<xsl:value-of select="$face_id"/>,
              nTrVisible(<xsl:value-of select="$nTrVisible"/>) is greater than
              nTr(<xsl:value-of select="$nTr"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>

    <!-- nTrHidden <= nTr -->
    <xsl:if test="t:TrianglesHidden|t:TrianglesHiddenBinary">

      <xsl:variable name="nTrHidden">
        <xsl:if test="t:TrianglesHidden">
          <xsl:value-of select="t:TrianglesHidden/@count"/>
        </xsl:if>
        <xsl:if test="t:TrianglesHiddenBinary">
          <xsl:value-of select="t:TrianglesHiddenBinary/@count"/>
        </xsl:if>
      </xsl:variable>

      <xsl:if test="not($nTrHidden &lt;= $nTr)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              FaceMesh: id=<xsl:value-of select="$face_id"/>,
              nTrHidden(<xsl:value-of select="$nTrHidden"/>) is greater than
              nTr(<xsl:value-of select="$nTr"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>

    <!-- nTrColor = nTr -->
    <xsl:if test="t:TrianglesColor|t:TrianglesColorBinary">

      <xsl:variable name="nTrColor">
        <xsl:if test="t:TrianglesColor">
          <xsl:value-of select="t:TrianglesColor/@count"/>
        </xsl:if>
        <xsl:if test="t:TrianglesColorBinary">
          <xsl:value-of select="t:TrianglesColorBinary/@count"/>
        </xsl:if>
      </xsl:variable>

      <xsl:if test="not($nTrColor = $nTr)">
        <xsl:for-each select=".">
          <xsl:call-template name="error_node">
            <xsl:with-param name="report">
              FaceMesh: id=<xsl:value-of select="$face_id"/>,
              nTrColor(<xsl:value-of select="$nTrColor"/>) !=
              nTr(<xsl:value-of select="$nTr"/>)
            </xsl:with-param>
          </xsl:call-template>
        </xsl:for-each>
      </xsl:if>
    </xsl:if>

    <xsl:apply-templates mode="Format"/>

  </xsl:template>
  
  <!--
  Return: number of triangle in FaceMesh.
  If Triangles and TrianglesBinary not exists then get number of triangles from underlying MeshTriangle.
  -->
  <xsl:template name="facemesh_n_tr">
    <xsl:param name="facemesh"/>
    <xsl:choose>
      <xsl:when test="$facemesh/t:Triangles">
        <xsl:value-of select="$facemesh/t:Triangles/@count"/>
      </xsl:when>
      <xsl:when test="$facemesh/t:TrianglesBinary">
        <xsl:value-of select="$facemesh/t:TrianglesBinary/@count"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:call-template name="meshtriangle_n_tr">
          <xsl:with-param name="mesh_id" select="$facemesh/t:Mesh/t:Id/text()"/>
        </xsl:call-template>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!--
  Return: number of triangle in MeshTriangle. 
  -->
  <xsl:template name="meshtriangle_n_tr">
    <xsl:param name="mesh_id"/>
    <xsl:for-each select="/t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceMeshSet/t:MeshTriangle[@id=$mesh_id]/t:MeshTriangleCore">
      <xsl:if test="t:Triangles">
        <xsl:value-of select="t:Triangles/@count"/>
      </xsl:if>
      <xsl:if test="t:TrianglesBinary">
        <xsl:value-of select="t:TrianglesBinary/@count"/>
      </xsl:if>
    </xsl:for-each>
  </xsl:template>

  <!--<xsl:template
    match="/t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:FaceMesh
         | /t:QIFDocument/t:Product/t:TopologySet/t:FaceSet/t:Face
    "
    mode="Format">

    facemesh_2 = <xsl:value-of select="@id"/>,
    vendor = <xsl:value-of select="system-property('xsl:vendor')"/>,
    version = <xsl:value-of select="system-property('xsl:version')"/>

    <xsl:apply-templates mode="Format"/>
  
  </xsl:template>-->

  <xsl:template
    match="/t:QIFDocument/t:Product/t:GeometrySet/t:Curve12Set/t:Nurbs12/t:Nurbs12Core
         | /t:QIFDocument/t:Product/t:GeometrySet/t:Curve13Set/t:Nurbs13/t:Nurbs13Core"
                mode="Format">
    <xsl:call-template name="check_nurbs1x_ncp_nkt_nwt"/>
    <xsl:call-template name="check_nurbs_ncp_nwt"/>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

  <xsl:template
  match="/t:QIFDocument/t:Product/t:GeometrySet/t:SurfaceSet/t:Nurbs23/t:Nurbs23Core"
              mode="Format">
    <xsl:call-template name="check_nurbs23_ncp_nkt_nwt"/>
    <xsl:call-template name="check_nurbs_ncp_nwt"/>
    <xsl:apply-templates mode="Format"/>
  </xsl:template>

  </xsl:stylesheet>
