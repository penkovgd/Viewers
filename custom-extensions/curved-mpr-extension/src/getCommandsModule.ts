import { DicomMetadataStore, utils } from '@ohif/core';

export default function getCommandsModule({ servicesManager, commandsManager, extensionManager }) {
  const { displaySetService, measurementService } = servicesManager.services;
  const actions = {
    sendMeasurments: async () => {
      const { filterTool } = utils.MeasurementFilters;
      const measurementData = measurementService.getMeasurements(filterTool('Probe'));
      console.log('Got measurments:', measurementData);

      // Для скорости тестирования убрал эту проверку
      // if (measurementData.length < 2) {
      // throw new Error('At least 2 points required');
      // console.error('At least 2 points required');
      // return;
      // }

      const StudyInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019';
      // const SeriesInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810150182600001560'; // малленкая серия (1 инстанс)
      const SeriesInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810501260100009281'; // большая серия (800 инстансов)
      const dataSource = extensionManager.getActiveDataSource()[0];
      const series = await dataSource.retrieve.series.metadata({ StudyInstanceUID });
      const SeriesRetrieveURL = series.find(
        s => s.SeriesInstanceUID === SeriesInstanceUID
      ).RetrieveURL;
      console.log(SeriesRetrieveURL); // http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019/series/1.3.12.2.1107.5.1.4.76270.30000024122810501260100009281?accept=application/zip

      try {
        // Получаем zip
        const zipResponse = await fetch(SeriesRetrieveURL + '?accept=application/zip', {
          method: 'GET',
          headers: {
            Accept: 'application/zip',
          },
        });
        if (!zipResponse.ok) {
          throw new Error(`DICOM fetch error: ${zipResponse.status} ${zipResponse.statusText}`);
        }

        const zipBlob = await zipResponse.blob();

        const formData = new FormData();

        // Добавляем zip в тело запроса
        formData.append('dicom_series', zipBlob, 'series.zip');

        // Добавляем точки в тело запроса
        formData.append(
          'measurements',
          JSON.stringify(JSON.stringify({ measurements: measurementData }))
        );

        // https://httpbin.org/post
        // http://127.0.0.1:8000/generate_mpr/
        const response = await fetch('http://127.0.0.1:8000/generate_mpr/', {
          method: 'POST',
          body: formData,
        });
        if (!response.ok) {
          throw new Error(`Backend error: ${response.status} ${response.statusText}`);
        }

        // Сохраняем abc.dcm от бекенда
        const arrayBuffer = await response.arrayBuffer();
        await dataSource.store.dicom(arrayBuffer);

        const promiseId = 'DCM4CHEE:1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019'; // хардкод
        dataSource.deleteStudyMetadataPromise(promiseId);
        const instances = await dataSource.retrieve.series.metadata({ StudyInstanceUID });
        console.log('ok');
      } catch (error) {
        console.error('Fetch operation failed:', error);
      }

      // DicomMetadataStore.addInstances(series);
      // const series = await dataSource.query.series.search(StudyInstanceUID);
      // DicomMetadataStore.addInstance(arrayBuffer);
      // console.log('ok');

      // Через filesToStudies
      // const blob = await response.blob();
      // const res = await filesToStudies([blob]);
      // console.log('ok');

      // const displaySets = displaySetService.getActiveDisplaySets();
      // for (const ds of displaySets) {
      //   displaySetService.setDisplaySetMetadataInvalidated(ds.displaySetInstanceUID);
      // }

      // // Получаем метаданные study от DicomMetadataStore
      // const studyMetadata = DicomMetadataStore.getStudy(StudyInstanceUID);
      // console.log('Study metada from DicomMetadataStore:', studyMetadata);

      // // Получаем метаданные от dataSource

      // Фетчим новые series
      // const dataSource = extensionManager.getActiveDataSource()[0];
      // console.log('datasource', dataSource);
      // // current study qido
      // const qidoForStudyUID = await dataSource.query.series.search(
      //   '1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019'
      // );

      // const study_1 = DicomMetadataStore.getStudy(StudyInstanceUID);
      // DicomMetadataStore.addStudy('1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019');
      // DicomMetadataStore.addInstances([{ StudyInstanceUID, SeriesInstanceUID }], true);
      // const study_2 = DicomMetadataStore.getStudy(
      //   '1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019'
      // );
      // console.log(study_1);

      // try to fetch the prior studies based on the patientID if the
      // server can respond.
      // const mrn = qidoForStudyUID[0].mrn;

      // await dataSource.query.studies.search({
      //   patientId: mrn,
      //   disableWildcard: true,
      // });

      // const seriesMetadata = await dataSource.retrieve.series.metadata({ StudyInstanceUID });
      // console.log('Series Metadata from dataSource:', seriesMetadata);
    },
  };
  const definitions = {
    sendMeasurments: {
      commandFn: actions.sendMeasurments,
    },
  };
  return {
    actions,
    definitions,
    defaultContext: 'ROUTE:VIEWER',
  };
}
